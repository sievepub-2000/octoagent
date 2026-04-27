"""Distributed execution control plane gateway router.

Exposes the ExecutionNodeRegistry for operator management: register/deregister
nodes, heartbeat, health checks, and task routing decisions.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from src.distributed_execution import get_execution_node_registry
from src.gateway.security import require_operator_or_403, require_worker_token_or_403
from src.operator_governance import confirmation_matches, redact_secrets, signed_audit_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/execution-nodes", tags=["distributed_execution"])


# ── Models ─────────────────────────────────────────────────────────────────────

class ExecutionNodeResponse(BaseModel):
    node_id: str
    address: str
    status: str
    capacity: int
    current_load: int
    available_capacity: int
    tags: list[str] = Field(default_factory=list)
    last_heartbeat: float
    is_healthy: bool
    metadata: dict[str, object] = Field(default_factory=dict)


class ExecutionNodesListResponse(BaseModel):
    nodes: list[ExecutionNodeResponse] = Field(default_factory=list)
    total: int = 0
    healthy_count: int = 0


class RegisterNodeRequest(BaseModel):
    node_id: str
    address: str
    capacity: int = 10
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    actor: str = "operator"
    operator_role: str = "operator"


class HeartbeatRequest(BaseModel):
    load: int = 0


class RouteTaskRequest(BaseModel):
    task_id: str
    affinity_node: str | None = None


class RouteTaskResponse(BaseModel):
    task_id: str
    target_node_id: str | None = None
    strategy: str
    reason: str


class DispatchTaskRequest(BaseModel):
    task_id: str
    payload: dict[str, object] = Field(default_factory=dict)
    affinity_node: str | None = None
    timeout_seconds: float = Field(default=10.0, ge=0.1, le=120)
    callback_url: str | None = None
    actor: str = "operator"
    operator_role: str = "operator"


class DispatchTaskResponse(BaseModel):
    dispatch_id: str
    task_id: str
    target_node_id: str | None = None
    status: str
    strategy: str
    reason: str = ""
    lease_id: str = ""
    attempts: list[dict[str, object]] = Field(default_factory=list)
    result: dict[str, object] = Field(default_factory=dict)
    error: str | None = None
    created_at: float
    updated_at: float | None = None
    audit: dict[str, object] = Field(default_factory=dict)


class WorkerDispatchRequest(BaseModel):
    dispatch_id: str
    lease_id: str = ""
    task_id: str
    payload: dict[str, object] = Field(default_factory=dict)
    callback_url: str | None = None
    callback_token: str | None = None


class WorkerDispatchResponse(BaseModel):
    accepted: bool = True
    worker_node_id: str = "local"
    dispatch_id: str
    lease_id: str = ""
    task_id: str
    result: dict[str, object] = Field(default_factory=dict)


class DispatchResultCallbackRequest(BaseModel):
    dispatch_id: str
    lease_id: str = ""
    node_id: str = ""
    status: str = "completed"
    result: dict[str, object] = Field(default_factory=dict)
    error: str | None = None


class ReplayDispatchRequest(BaseModel):
    timeout_seconds: float = Field(default=10.0, ge=0.1, le=120)
    actor: str = "operator"
    operator_role: str = "operator"
    confirmation: str = ""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _node_to_response(n) -> ExecutionNodeResponse:
    return ExecutionNodeResponse(
        node_id=n.node_id,
        address=n.address,
        status=n.status,
        capacity=n.capacity,
        current_load=n.current_load,
        available_capacity=n.available_capacity,
        tags=n.tags,
        last_heartbeat=n.last_heartbeat,
        is_healthy=n.is_healthy,
        metadata=redact_secrets(n.metadata),
    )


def _dispatch_response(result, *, event: str = "distributed.dispatch") -> DispatchTaskResponse:
    payload = get_execution_node_registry().result_to_dict(result)
    payload["result"] = redact_secrets(payload.get("result") or {})
    payload["audit"] = signed_audit_event(
        event,
        dispatch_id=result.dispatch_id,
        task_id=result.task_id,
        node_id=result.target_node_id,
        status=result.status,
    )
    return DispatchTaskResponse.model_validate(payload)


def _require_operator(*, role: str | None, token: str | None, minimum: str = "operator") -> None:
    require_operator_or_403(role=role, token=token, minimum=minimum)


def _validate_http_url(url: str | None, *, field_name: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be an absolute http(s) URL")
    return url


def _validate_node_address(address: str) -> str:
    address = (address or "").strip()
    if not address:
        raise HTTPException(status_code=400, detail="Node address is required")
    parsed = urlparse(address)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Node address scheme must be http or https")
    return address


def _require_worker_token(provided: str | None) -> None:
    require_worker_token_or_403(provided)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=ExecutionNodesListResponse)
async def list_nodes() -> ExecutionNodesListResponse:
    """List all registered execution nodes."""
    reg = get_execution_node_registry()
    nodes = reg.list_nodes()
    healthy = reg.healthy_nodes()
    return ExecutionNodesListResponse(
        nodes=[_node_to_response(n) for n in nodes],
        total=len(nodes),
        healthy_count=len(healthy),
    )


@router.post("", response_model=ExecutionNodeResponse, status_code=201)
async def register_node(
    request: RegisterNodeRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
) -> ExecutionNodeResponse:
    """Register a new execution node."""
    from src.distributed_execution import ExecutionNode
    _require_operator(role=request.operator_role, token=x_octoagent_operator_token)
    reg = get_execution_node_registry()
    node = ExecutionNode(
        node_id=request.node_id,
        address=_validate_node_address(request.address),
        capacity=request.capacity,
        tags=request.tags,
        metadata=request.metadata,
    )
    reg.register(node)
    return _node_to_response(node)


@router.delete("/{node_id}", status_code=204)
async def deregister_node(
    node_id: str,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
    x_octoagent_operator_role: str | None = Header(default="operator", alias="X-OctoAgent-Operator-Role"),
) -> None:
    """Remove an execution node from the registry."""
    _require_operator(role=x_octoagent_operator_role, token=x_octoagent_operator_token)
    reg = get_execution_node_registry()
    nodes_before = {n.node_id for n in reg.list_nodes()}
    if node_id not in nodes_before:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    reg.deregister(node_id)


@router.post("/{node_id}/heartbeat", response_model=ExecutionNodeResponse)
async def node_heartbeat(node_id: str, request: HeartbeatRequest) -> ExecutionNodeResponse:
    """Record a heartbeat for an execution node."""
    reg = get_execution_node_registry()
    nodes_map = {n.node_id: n for n in reg.list_nodes()}
    if node_id not in nodes_map:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    reg.heartbeat(node_id, load=request.load)
    return _node_to_response(nodes_map[node_id])


@router.get("/{node_id}", response_model=ExecutionNodeResponse)
async def get_node(node_id: str) -> ExecutionNodeResponse:
    """Get detail for a specific execution node."""
    reg = get_execution_node_registry()
    nodes_map = {n.node_id: n for n in reg.list_nodes()}
    if node_id not in nodes_map:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return _node_to_response(nodes_map[node_id])


@router.post("/route", response_model=RouteTaskResponse)
async def route_task(request: RouteTaskRequest) -> RouteTaskResponse:
    """Determine the best execution node for a task."""
    reg = get_execution_node_registry()
    decision = reg.route_task(request.task_id, affinity_node=request.affinity_node)
    return RouteTaskResponse(
        task_id=decision.task_id,
        target_node_id=decision.target_node_id,
        strategy=decision.strategy,
        reason=decision.reason,
    )


@router.post("/dispatch", response_model=DispatchTaskResponse)
async def dispatch_task(
    request: DispatchTaskRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
) -> DispatchTaskResponse:
    """Dispatch a task to a remote worker endpoint with local fallback/failover."""
    _require_operator(role=request.operator_role, token=x_octoagent_operator_token)
    callback_url = _validate_http_url(request.callback_url, field_name="callback_url")
    reg = get_execution_node_registry()
    result = await reg.dispatch_task(
        request.task_id,
        dict(request.payload),
        affinity_node=request.affinity_node,
        timeout_seconds=request.timeout_seconds,
        callback_url=callback_url,
    )
    return _dispatch_response(result)


@router.get("/history/dispatches", response_model=list[DispatchTaskResponse])
async def list_dispatches() -> list[DispatchTaskResponse]:
    """Return recent distributed dispatch attempts and results."""
    reg = get_execution_node_registry()
    return [_dispatch_response(item, event="distributed.dispatch.history") for item in reg.list_dispatches()]


@router.post("/dispatches/{dispatch_id}/result", response_model=DispatchTaskResponse)
async def record_dispatch_result(
    dispatch_id: str,
    request: DispatchResultCallbackRequest,
    x_execution_node_token: str | None = Header(default=None, alias="X-Execution-Node-Token"),
) -> DispatchTaskResponse:
    """Accept worker result callbacks. Token is checked when the node registered one."""
    reg = get_execution_node_registry()
    nodes = {node.node_id: node for node in reg.list_nodes()}
    node = nodes.get(request.node_id)
    expected_token = str((node.metadata or {}).get("callback_token") or (node.metadata or {}).get("dispatch_token") or "") if node else ""
    if expected_token:
        if x_execution_node_token != expected_token:
            raise HTTPException(status_code=403, detail="Invalid execution node callback token")
    else:
        _require_worker_token(x_execution_node_token)
    result = reg.update_dispatch_result(
        dispatch_id,
        status="completed" if request.status == "completed" else "failed",
        result=dict(request.result),
        error=request.error,
        node_id=request.node_id or None,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Dispatch '{dispatch_id}' not found")
    return _dispatch_response(result, event="distributed.dispatch.result_callback")


@router.post("/dispatches/{dispatch_id}/replay", response_model=DispatchTaskResponse)
async def replay_dispatch(
    dispatch_id: str,
    request: ReplayDispatchRequest,
    x_octoagent_operator_token: str | None = Header(default=None, alias="X-OctoAgent-Operator-Token"),
) -> DispatchTaskResponse:
    """Replay a previous dispatch through the current healthy-node routing policy."""
    _require_operator(role=request.operator_role, token=x_octoagent_operator_token)
    if not confirmation_matches("REPLAY DISPATCH", request.confirmation):
        raise HTTPException(status_code=409, detail="Replay requires confirmation: CONFIRM REPLAY DISPATCH")
    result = await get_execution_node_registry().replay_dispatch(
        dispatch_id,
        timeout_seconds=request.timeout_seconds,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Dispatch '{dispatch_id}' not found")
    return _dispatch_response(result, event="distributed.dispatch.failover_replay")


@router.post("/worker/dispatch", response_model=WorkerDispatchResponse)
async def worker_dispatch(
    request: WorkerDispatchRequest,
    x_execution_node_token: str | None = Header(default=None, alias="X-Execution-Node-Token"),
) -> WorkerDispatchResponse:
    """Minimal worker endpoint used by real HTTP dispatch smoke and remote nodes."""
    _require_worker_token(x_execution_node_token)
    _validate_http_url(request.callback_url, field_name="callback_url")
    return WorkerDispatchResponse(
        dispatch_id=request.dispatch_id,
        lease_id=request.lease_id,
        task_id=request.task_id,
        result={
            "status": "completed",
            "echo": request.payload,
            "token_received": bool(x_execution_node_token),
        },
    )
