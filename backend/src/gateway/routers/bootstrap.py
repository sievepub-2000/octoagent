from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.bootstrap.runtime import get_embedded_bootstrap_runtime

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
    graphrag_enabled: bool
    retrieval_backend: str
    use_for_embeddings: bool
    vector_store_path: str
    graphrag_root: str
    graphrag_input_dir: str
    graphrag_output_dir: str
    graphrag_cli_available: bool
    graphrag_initialized: bool
    graphrag_index_ready: bool
    graphrag_query_method: str
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
    graphrag_initialized: bool
    graphrag_input_files: int


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
        graphrag_initialized=runtime.graphrag_store().is_initialized(),
        graphrag_input_files=len(list(runtime.graphrag_store().input_dir.glob("*.md"))),
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
