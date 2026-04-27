"""Distributed execution contracts for multi-node task dispatching.

P3 module — defines the execution node registry, task routing,
and health-check contracts for distributing workspace execution
across multiple backend instances.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ExecutionNode:
    """A backend instance that can execute task workspaces."""

    node_id: str
    address: str  # host:port
    status: Literal["healthy", "degraded", "offline"] = "healthy"
    capacity: int = 10  # max concurrent tasks
    current_load: int = 0
    tags: list[str] = field(default_factory=list)
    last_heartbeat: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def available_capacity(self) -> int:
        return max(self.capacity - self.current_load, 0)

    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy" and (time.time() - self.last_heartbeat) < 60


@dataclass
class TaskRoutingDecision:
    """Result of routing a task to an execution node."""

    task_id: str
    target_node_id: str | None
    strategy: Literal["round_robin", "least_loaded", "affinity", "local", "unavailable"] = "local"
    reason: str = ""


@dataclass
class ExecutionDispatchResult:
    dispatch_id: str
    task_id: str
    target_node_id: str | None
    status: Literal["completed", "accepted", "failed", "unavailable", "replayed"]
    strategy: str
    reason: str = ""
    lease_id: str = ""
    attempts: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class ExecutionNodeRegistry:
    """Registry of distributed execution nodes."""

    def __init__(self) -> None:
        self._nodes: dict[str, ExecutionNode] = {}
        self._dispatches: list[ExecutionDispatchResult] = []
        # Default: single local node
        self._nodes["local"] = ExecutionNode(
            node_id="local",
            address="127.0.0.1:19882",
            capacity=50,
        )

    def register(self, node: ExecutionNode) -> None:
        node.last_heartbeat = time.time()
        self._nodes[node.node_id] = node

    def deregister(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)

    def heartbeat(self, node_id: str, load: int = 0) -> None:
        node = self._nodes.get(node_id)
        if node is not None:
            node.last_heartbeat = time.time()
            node.current_load = load
            node.status = "healthy"

    def healthy_nodes(self) -> list[ExecutionNode]:
        return [n for n in self._nodes.values() if n.is_healthy]

    def route_task(self, task_id: str, *, affinity_node: str | None = None) -> TaskRoutingDecision:
        """Route a task to the best available execution node."""
        healthy = self.healthy_nodes()
        if not healthy:
            return TaskRoutingDecision(
                task_id=task_id,
                target_node_id="local",
                strategy="local",
                reason="No healthy nodes, falling back to local",
            )

        # Prefer affinity node if healthy
        if affinity_node is not None:
            node = self._nodes.get(affinity_node)
            if node is not None and node.is_healthy and node.available_capacity > 0:
                return TaskRoutingDecision(
                    task_id=task_id,
                    target_node_id=node.node_id,
                    strategy="affinity",
                    reason=f"Affinity to {node.node_id}",
                )

        candidates = [node for node in healthy if node.available_capacity > 0]
        if not candidates:
            return TaskRoutingDecision(
                task_id=task_id,
                target_node_id=None,
                strategy="unavailable",
                reason="All healthy nodes are at capacity",
            )

        # Least-loaded strategy among nodes that can still accept work.
        best = min(candidates, key=lambda n: n.current_load)
        return TaskRoutingDecision(
            task_id=task_id,
            target_node_id=best.node_id,
            strategy="least_loaded",
            reason=f"Least loaded: {best.node_id} (load={best.current_load}/{best.capacity})",
        )

    def list_nodes(self) -> list[ExecutionNode]:
        return list(self._nodes.values())

    def list_dispatches(self) -> list[ExecutionDispatchResult]:
        return list(self._dispatches[:100])

    def get_dispatch(self, dispatch_id: str) -> ExecutionDispatchResult | None:
        return next((item for item in self._dispatches if item.dispatch_id == dispatch_id), None)

    @staticmethod
    def _node_dispatch_url(node: ExecutionNode) -> str:
        address = node.address.strip()
        if not address.startswith(("http://", "https://")):
            address = f"http://{address}"
        return f"{address.rstrip('/')}/api/execution-nodes/worker/dispatch"

    async def dispatch_task(
        self,
        task_id: str,
        payload: dict[str, Any],
        *,
        affinity_node: str | None = None,
        timeout_seconds: float = 10.0,
        callback_url: str | None = None,
    ) -> ExecutionDispatchResult:
        decision = self.route_task(task_id, affinity_node=affinity_node)
        dispatch_id = f"dispatch-{uuid.uuid4()}"
        lease_id = f"lease-{uuid.uuid4()}"
        resolved_callback_url = None
        if callback_url:
            base = callback_url.rstrip("/")
            if not base.endswith(f"/dispatches/{dispatch_id}/result"):
                base = f"{base}/api/execution-nodes/dispatches/{dispatch_id}/result"
            resolved_callback_url = base
        candidates: list[ExecutionNode] = []
        if decision.target_node_id and decision.target_node_id in self._nodes:
            candidates.append(self._nodes[decision.target_node_id])
        candidates.extend(
            node
            for node in sorted(self.healthy_nodes(), key=lambda item: item.current_load)
            if node.node_id not in {candidate.node_id for candidate in candidates} and node.available_capacity > 0
        )
        if not candidates:
            result = ExecutionDispatchResult(
                dispatch_id=dispatch_id,
                task_id=task_id,
                target_node_id=None,
                status="unavailable",
                strategy=decision.strategy,
                reason=decision.reason,
                error="No healthy node with available capacity.",
                lease_id=lease_id,
            )
            self._record_dispatch(result)
            return result

        attempts: list[dict[str, Any]] = []
        for node in candidates:
            node.current_load += 1
            try:
                if node.node_id == "local":
                    result_payload = {
                        "accepted": True,
                        "worker_node_id": "local",
                        "task_id": task_id,
                        "mode": "local-inline",
                        "payload": payload,
                    }
                else:
                    headers = {}
                    if token := node.metadata.get("dispatch_token"):
                        headers["X-Execution-Node-Token"] = str(token)
                    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                        response = await client.post(
                            self._node_dispatch_url(node),
                            json={
                                "dispatch_id": dispatch_id,
                                "lease_id": lease_id,
                                "task_id": task_id,
                                "payload": payload,
                                "callback_url": resolved_callback_url,
                                "callback_token": node.metadata.get("callback_token") or node.metadata.get("dispatch_token"),
                            },
                            headers=headers,
                        )
                    response.raise_for_status()
                    result_payload = response.json()
                attempts.append({"node_id": node.node_id, "status": "completed"})
                result = ExecutionDispatchResult(
                    dispatch_id=dispatch_id,
                    task_id=task_id,
                    target_node_id=node.node_id,
                    status="completed",
                    strategy=decision.strategy,
                    reason=decision.reason,
                    lease_id=lease_id,
                    attempts=attempts,
                    result=result_payload if isinstance(result_payload, dict) else {"result": result_payload},
                )
                self._record_dispatch(result)
                return result
            except Exception as exc:
                logger.warning("Distributed dispatch failed on node %s: %s", node.node_id, exc)
                node.status = "degraded"
                attempts.append({"node_id": node.node_id, "status": "failed", "error": str(exc)})
            finally:
                node.current_load = max(0, node.current_load - 1)

        result = ExecutionDispatchResult(
            dispatch_id=dispatch_id,
            task_id=task_id,
            target_node_id=None,
            status="failed",
            strategy=decision.strategy,
            reason="All candidate nodes failed dispatch.",
            lease_id=lease_id,
            attempts=attempts,
            error=attempts[-1].get("error") if attempts else "dispatch_failed",
        )
        self._record_dispatch(result)
        return result

    def _record_dispatch(self, result: ExecutionDispatchResult) -> None:
        self._dispatches.insert(0, result)
        del self._dispatches[100:]

    def update_dispatch_result(
        self,
        dispatch_id: str,
        *,
        status: Literal["completed", "accepted", "failed"],
        result: dict[str, Any] | None = None,
        error: str | None = None,
        node_id: str | None = None,
    ) -> ExecutionDispatchResult | None:
        dispatch = self.get_dispatch(dispatch_id)
        if dispatch is None:
            return None
        dispatch.status = status
        dispatch.result = dict(result or dispatch.result or {})
        dispatch.error = error
        dispatch.updated_at = time.time()
        if node_id:
            dispatch.target_node_id = node_id
        return dispatch

    async def replay_dispatch(
        self,
        dispatch_id: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> ExecutionDispatchResult | None:
        previous = self.get_dispatch(dispatch_id)
        if previous is None:
            return None
        nested_result = previous.result.get("result") if isinstance(previous.result.get("result"), dict) else {}
        payload = dict(nested_result.get("echo") or previous.result.get("echo") or previous.result.get("payload") or {})
        if not payload:
            payload = {"replay_of": dispatch_id}
        replay = await self.dispatch_task(
            previous.task_id,
            payload,
            timeout_seconds=timeout_seconds,
        )
        replay.status = "replayed" if replay.status == "completed" else replay.status
        replay.reason = f"Failover replay of {dispatch_id}: {replay.reason}"
        return replay

    @staticmethod
    def result_to_dict(result: ExecutionDispatchResult) -> dict[str, Any]:
        return asdict(result)


_registry: ExecutionNodeRegistry | None = None


def get_execution_node_registry() -> ExecutionNodeRegistry:
    global _registry
    if _registry is None:
        _registry = ExecutionNodeRegistry()
    return _registry
