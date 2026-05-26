from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.runtime.bootstrap.runtime import get_embedded_bootstrap_runtime

router = APIRouter(prefix="/api/bootstrap", tags=["bootstrap"])


class BootstrapStatusResponse(BaseModel):
    enabled: bool
    project_managed: bool
    framework: str
    repo_id: str
    filename: str
    model_path: str
    installed: bool
    onboarding_enabled: bool
    use_for_embeddings: bool
    vector_store_path: str
    starter_prompts: list[str]
    documents: int
    namespaces: int
    n_ctx: int
    n_batch: int
    n_threads: int
    recommended_model: str
    size_bytes: int | None = None
    corpus_files: list[str]


class BootstrapGuideRequest(BaseModel):
    user_goal: str | None = Field(default=None)
    workspace_summary: str | None = Field(default=None)


class BootstrapGuideResponse(BaseModel):
    message: str
    suggestions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class BootstrapInstallResponse(BaseModel):
    installed: bool
    model_path: str
    documents: int
    namespaces: int


@router.get(
    "/status",
    response_model=BootstrapStatusResponse,
    summary="Get Embedded Bootstrap Model Status",
)
async def get_bootstrap_status() -> BootstrapStatusResponse:
    runtime = get_embedded_bootstrap_runtime()
    return BootstrapStatusResponse(**runtime.status())


@router.post(
    "/install",
    response_model=BootstrapInstallResponse,
    summary="Install Embedded Bootstrap Model",
)
async def install_bootstrap_model() -> BootstrapInstallResponse:
    runtime = get_embedded_bootstrap_runtime()
    path = runtime.ensure_installed()
    runtime.seed_default_documents()
    stats = runtime.sync_local_corpus()
    return BootstrapInstallResponse(
        installed=path.exists(),
        model_path=str(path),
        documents=stats["documents"],
        namespaces=stats["namespaces"],
    )


@router.post(
    "/guide",
    response_model=BootstrapGuideResponse,
    summary="Generate Embedded Startup Guide",
)
async def generate_bootstrap_guide(
    request: BootstrapGuideRequest,
) -> BootstrapGuideResponse:
    runtime = get_embedded_bootstrap_runtime()
    result = runtime.generate_guide(
        user_goal=request.user_goal,
        workspace_summary=request.workspace_summary,
    )
    return BootstrapGuideResponse(**result)
