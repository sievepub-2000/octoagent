"""Gateway router for browser runtime capabilities and seed sessions."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from src.tools.sandbox.browser import (
    BrowserActionExecutionRequest,
    BrowserActionExecutionResult,
    BrowserExecutionSession,
    BrowserProviderProfile,
    BrowserRuntimeCapability,
    BrowserSessionRecoveryRequest,
    BrowserSessionRequest,
    BrowserSessionUpdateRequest,
    get_browser_runtime_service,
)

router = APIRouter(prefix="/api/browser-runtime", tags=["browser-runtime"])


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@router.get("/capabilities", response_model=BrowserRuntimeCapability)
async def get_browser_runtime_capabilities() -> BrowserRuntimeCapability:
    return get_browser_runtime_service().get_capability()


@router.get("/providers", response_model=list[BrowserProviderProfile])
async def list_browser_runtime_providers() -> list[BrowserProviderProfile]:
    return get_browser_runtime_service().list_provider_profiles()


@router.get("/sessions", response_model=list[BrowserExecutionSession])
async def list_browser_runtime_sessions() -> list[BrowserExecutionSession]:
    return get_browser_runtime_service().list_sessions()


@router.post("/sessions", response_model=BrowserExecutionSession)
async def create_browser_runtime_session(
    request: BrowserSessionRequest,
) -> BrowserExecutionSession:
    return get_browser_runtime_service().create_session(request, created_at=utc_now())


@router.get("/sessions/{session_id}", response_model=BrowserExecutionSession)
async def get_browser_runtime_session(session_id: str) -> BrowserExecutionSession:
    session = get_browser_runtime_service().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Browser session '{session_id}' not found")
    return session


@router.post("/sessions/{session_id}/status", response_model=BrowserExecutionSession)
async def update_browser_runtime_session(
    session_id: str,
    request: BrowserSessionUpdateRequest,
) -> BrowserExecutionSession:
    session = get_browser_runtime_service().update_session(session_id, request, updated_at=utc_now())
    if session is None:
        raise HTTPException(status_code=404, detail=f"Browser session '{session_id}' not found")
    return session


@router.post("/sessions/{session_id}/execute-next", response_model=BrowserActionExecutionResult)
async def execute_next_browser_runtime_action(
    session_id: str,
    request: BrowserActionExecutionRequest,
) -> BrowserActionExecutionResult:
    result = get_browser_runtime_service().execute_next_action(session_id, request, executed_at=utc_now())
    if result is None:
        raise HTTPException(status_code=404, detail=f"Browser session '{session_id}' not found")
    return result


@router.post("/sessions/{session_id}/recover", response_model=BrowserExecutionSession)
async def recover_browser_runtime_session(
    session_id: str,
    request: BrowserSessionRecoveryRequest,
) -> BrowserExecutionSession:
    session = get_browser_runtime_service().recover_session(session_id, request, recovered_at=utc_now())
    if session is None:
        raise HTTPException(status_code=404, detail=f"Browser session '{session_id}' not found")
    return session
