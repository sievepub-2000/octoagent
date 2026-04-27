"""Gateway router for research runtime capabilities and experiment seeds."""

from fastapi import APIRouter, HTTPException

from src.research_runtime import (
    CreateResearchExperimentRequest,
    ResearchExperiment,
    ResearchExperimentListResponse,
    ResearchExperimentRunResponse,
    ResearchProgramListResponse,
    ResearchRuntimeCapability,
    ResearchRuntimeStatusResponse,
    ResearchTrial,
    RunResearchExperimentRequest,
    get_research_runtime_service,
)
from src.workflow_core import utc_now

router = APIRouter(prefix="/api/research-runtime", tags=["research-runtime"])


@router.get("/capabilities", response_model=ResearchRuntimeCapability)
async def get_research_runtime_capabilities() -> ResearchRuntimeCapability:
    return get_research_runtime_service().get_capability()


@router.get("/status", response_model=ResearchRuntimeStatusResponse)
async def get_research_runtime_status() -> ResearchRuntimeStatusResponse:
    return ResearchRuntimeStatusResponse(
        snapshot=get_research_runtime_service().get_runtime_snapshot()
    )


@router.get("/programs", response_model=ResearchProgramListResponse)
async def list_research_programs() -> ResearchProgramListResponse:
    return get_research_runtime_service().list_programs()


@router.get("/experiments", response_model=ResearchExperimentListResponse)
async def list_research_experiments() -> ResearchExperimentListResponse:
    return get_research_runtime_service().list_experiments()


@router.post("/experiments", response_model=ResearchExperiment)
async def create_research_experiment(
    request: CreateResearchExperimentRequest,
) -> ResearchExperiment:
    return get_research_runtime_service().create_experiment(request, created_at=utc_now())


@router.get("/experiments/{experiment_id}", response_model=ResearchExperiment)
async def get_research_experiment(experiment_id: str) -> ResearchExperiment:
    experiment = get_research_runtime_service().get_experiment(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail=f"Research experiment '{experiment_id}' not found")
    return experiment


@router.get("/experiments/{experiment_id}/trials", response_model=list[ResearchTrial])
async def list_research_trials(experiment_id: str) -> list[ResearchTrial]:
    return get_research_runtime_service().list_trials(experiment_id)


@router.post("/experiments/{experiment_id}/run", response_model=ResearchExperimentRunResponse)
async def run_research_experiment(
    experiment_id: str,
    request: RunResearchExperimentRequest,
) -> ResearchExperimentRunResponse:
    response = get_research_runtime_service().run_experiment(
        experiment_id,
        request,
        created_at=utc_now(),
    )
    if response is None:
        raise HTTPException(status_code=404, detail=f"Research experiment '{experiment_id}' not found")
    return response
