"""Gateway router for query-engine capabilities and session surfaces."""

from fastapi import APIRouter, HTTPException

from src.agent_core import get_agent_core_service
from src.orchestration import get_orchestration_service
from src.query_engine import (
    QueryClientCommand,
    QueryEngineCapability,
    QueryOperationPlanRequest,
    QueryOperationPlanResponse,
    QuerySession,
    QuerySessionCompactRequest,
    QuerySessionGovernance,
    QuerySessionRefreshRequest,
    QueryTurnExecutionRequest,
    QueryTurnRecordRequest,
    get_query_engine_service,
)
from src.workflow_core import utc_now

router = APIRouter(prefix="/api/query-engine", tags=["query-engine"])

__all__ = [
    "QueryClientCommand",
    "QueryEngineCapability",
    "QueryOperationPlanRequest",
    "QueryOperationPlanResponse",
    "QuerySession",
    "QuerySessionGovernance",
    "router",
]


@router.get("/capabilities", response_model=QueryEngineCapability)
async def get_query_engine_capabilities() -> QueryEngineCapability:
    return get_query_engine_service().get_capability()


@router.post("/plan-operation", response_model=QueryOperationPlanResponse)
async def plan_query_engine_operation(
    request: QueryOperationPlanRequest,
) -> QueryOperationPlanResponse:
    return get_query_engine_service().plan_operation(request)


@router.get("/sessions", response_model=list[QuerySession])
async def list_query_engine_sessions() -> list[QuerySession]:
    return get_query_engine_service().list_sessions()


@router.get("/maintenance")
async def get_query_engine_maintenance_snapshot() -> dict[str, object]:
    return get_query_engine_service().maintenance_snapshot()


@router.post("/maintenance/run")
async def run_query_engine_maintenance() -> dict[str, object]:
    return get_query_engine_service().run_maintenance(created_at=utc_now())


@router.post("/maintenance/recover-stale")
async def recover_stale_query_engine_sessions() -> dict[str, object]:
    return get_query_engine_service().recover_stale_sessions(created_at=utc_now())


@router.get("/sessions/{session_id}", response_model=QuerySession)
async def get_query_engine_session(session_id: str) -> QuerySession:
    session = get_query_engine_service().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Query session '{session_id}' not found")
    return session


@router.post("/sessions/{session_id}/summary-quality")
async def evaluate_query_engine_summary_quality(session_id: str) -> dict[str, object]:
    result = get_query_engine_service().evaluate_summary_quality(session_id, created_at=utc_now())
    if result is None:
        raise HTTPException(status_code=404, detail=f"Query session '{session_id}' not found")
    return result


@router.get("/sessions/{session_id}/replay-context")
async def get_query_engine_replay_context(session_id: str) -> dict[str, object]:
    result = get_query_engine_service().build_replay_context(session_id, created_at=utc_now())
    if result is None:
        raise HTTPException(status_code=404, detail=f"Query session '{session_id}' not found")
    return result


@router.post("/sessions/{session_id}/turns", response_model=QuerySession)
async def record_query_engine_turn(
    session_id: str,
    request: QueryTurnRecordRequest,
) -> QuerySession:
    session = get_query_engine_service().record_turn(session_id, request, created_at=utc_now())
    if session is None:
        raise HTTPException(status_code=404, detail=f"Query session '{session_id}' not found")
    return session


@router.post("/sessions/{session_id}/recover", response_model=QuerySession)
async def recover_query_engine_session(
    session_id: str,
    request: QuerySessionRefreshRequest,
) -> QuerySession:
    session = get_query_engine_service().recover_session(
        session_id,
        created_at=utc_now(),
        reason=request.reason,
    )
    if session is None:
        raise HTTPException(status_code=404, detail=f"Query session '{session_id}' not found")
    return session


@router.post("/sessions/{session_id}/execute", response_model=QuerySession)
async def execute_query_engine_turn(
    session_id: str,
    request: QueryTurnExecutionRequest,
) -> QuerySession:
    session = get_query_engine_service().execute_turn(session_id, request, created_at=utc_now())
    if session is None:
        raise HTTPException(status_code=404, detail=f"Query session '{session_id}' not found")
    return session


@router.post("/sessions/{session_id}/compact", response_model=QuerySession)
async def compact_query_engine_session(
    session_id: str,
    request: QuerySessionCompactRequest,
) -> QuerySession:
    session = get_query_engine_service().compact_session(session_id, request, created_at=utc_now())
    if session is None:
        raise HTTPException(status_code=404, detail=f"Query session '{session_id}' not found")
    return session


@router.post("/sessions/{session_id}/refresh-profile", response_model=QuerySession)
async def refresh_query_engine_session_profile(
    session_id: str,
    request: QuerySessionRefreshRequest,
) -> QuerySession:
    session = get_query_engine_service().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Query session '{session_id}' not found")
    workspace, agent = get_agent_core_service().get_task_agent_context(session.task_id, session.agent_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Task workspace '{session.task_id}' not found")
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{session.agent_id}' not found")
    prompt_stack = get_orchestration_service().list_prompt_stacks()[0]
    refreshed = get_query_engine_service().refresh_session_profile(
        session_id,
        workspace,
        agent,
        prompt_stack,
        request,
        created_at=utc_now(),
    )
    if refreshed is None:
        raise HTTPException(status_code=404, detail=f"Query session '{session_id}' not found")
    return refreshed
