from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.brain import BrainCoreService, BrainResponse, BrainTaskContext
from src.brain.modules import BrainModuleDescriptor

router = APIRouter(prefix="/api/brain", tags=["brain"])


class BrainPlanRequest(BaseModel):
    thread_id: str | None = Field(default=None)
    user_goal: str
    constraints: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    preferred_mode: str = Field(default="plan")
    factor_candidates: list[str] = Field(default_factory=list)
    risk_limits: list[str] = Field(default_factory=list)
    memory_hints: list[str] = Field(default_factory=list)


class BrainCapabilitiesResponse(BaseModel):
    modules: list[BrainModuleDescriptor] = Field(default_factory=list)
    supported_modes: list[str] = Field(
        default_factory=lambda: ["plan", "research", "quant", "policy"]
    )
    execution_backends: list[str] = Field(default_factory=lambda: ["workflow_contracts"])
    notes: list[str] = Field(default_factory=list)


@router.get(
    "/capabilities",
    response_model=BrainCapabilitiesResponse,
    summary="Describe Brain Core Capabilities",
    description="Expose registered Brain modules, supported modes, and current execution-backend surface.",
)
async def get_brain_capabilities() -> BrainCapabilitiesResponse:
    service = BrainCoreService()
    return BrainCapabilitiesResponse(
        modules=service.describe_modules(),
        notes=[
            "Brain Core currently ships structured planning, evidence routing, memory reasoning, quant scoping, and policy gating.",
            "Execution remains contract-driven; no direct autonomous strategy execution backend is wired into Brain Core yet.",
        ],
    )


@router.post(
    "/plan",
    response_model=BrainResponse,
    summary="Build Brain Core Plan",
    description="Run the Brain Core planner and return a structured plan, fusion graph, and validation report.",
)
async def build_brain_plan(request: BrainPlanRequest) -> BrainResponse:
    service = BrainCoreService()
    context = BrainTaskContext(
        thread_id=request.thread_id,
        user_goal=request.user_goal,
        constraints=request.constraints,
        evidence=request.evidence,
        preferred_mode=request.preferred_mode,  # type: ignore[arg-type]
        factor_candidates=request.factor_candidates,
        risk_limits=request.risk_limits,
        memory_hints=request.memory_hints,
    )
    return service.run(context)
