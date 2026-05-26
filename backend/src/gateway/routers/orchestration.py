"""Gateway router for orchestration capability and compiled task graph surfaces."""

from fastapi import APIRouter

from src.harness.orchestration import (
    CompiledTaskGraph,
    OrchestrationCapability,
    PromptStackProfile,
    get_orchestration_service,
)

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


@router.get("/capabilities", response_model=OrchestrationCapability)
async def get_orchestration_capabilities() -> OrchestrationCapability:
    return get_orchestration_service().get_capability()


@router.get("/prompt-stacks", response_model=list[PromptStackProfile])
async def list_prompt_stacks() -> list[PromptStackProfile]:
    return get_orchestration_service().list_prompt_stacks()


@router.get("/graphs/seed", response_model=CompiledTaskGraph)
async def get_seed_task_graph() -> CompiledTaskGraph:
    return get_orchestration_service().get_seed_graph()
