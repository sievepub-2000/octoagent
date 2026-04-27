"""Configuration for the embedded tiny-model bootstrap runtime."""

from pydantic import BaseModel, Field


class EmbeddedModelConfig(BaseModel):
    """Configuration for the embedded local bootstrap model."""

    project_managed: bool = Field(
        default=True,
        description="Whether the embedded bootstrap assets live under a repository-owned system directory.",
    )

    enabled: bool = Field(
        default=True,
        description="Whether the embedded bootstrap model is enabled.",
    )
    framework: str = Field(
        default="llama_cpp",
        description="Inference framework used for the embedded model runtime.",
    )
    repo_id: str = Field(
        default="lmstudio-community/gemma-3-270m-it-GGUF",
        description="Model repository for the embedded GGUF model.",
    )
    filename: str = Field(
        default="gemma-3-270m-it-Q4_K_M.gguf",
        description="GGUF filename to download and run locally.",
    )
    cache_dir: str = Field(
        default="deploy/system/bootstrap/models",
        description="Directory where the embedded model files are stored.",
    )
    vector_store_path: str = Field(
        default="deploy/system/bootstrap/bootstrap_vectors.duckdb",
        description="Path to the DuckDB file used for bootstrap semantic retrieval.",
    )
    graphrag_root: str = Field(
        default="deploy/system/bootstrap/graphrag",
        description="Project-managed GraphRAG workspace used for bootstrap retrieval.",
    )
    onboarding_enabled: bool = Field(
        default=True,
        description="Whether to use the embedded model for startup guidance and onboarding hints.",
    )
    graphrag_enabled: bool = Field(
        default=True,
        description="Whether to prepare and query a GraphRAG project for bootstrap retrieval.",
    )
    retrieval_backend: str = Field(
        default="graphrag",
        description="Primary bootstrap retrieval backend. Supported values: graphrag, semantic.",
    )
    graphrag_query_method: str = Field(
        default="local",
        description="GraphRAG query method used for bootstrap retrieval.",
    )
    use_for_embeddings: bool = Field(
        default=True,
        description="Whether to reuse the embedded model for lightweight semantic embeddings.",
    )
    auto_download: bool = Field(
        default=False,
        description="Whether to automatically download the embedded model when first accessed.",
    )
    n_ctx: int = Field(default=8192, ge=512, le=32768)
    n_batch: int = Field(default=256, ge=32, le=4096)
    n_threads: int = Field(
        default=10,
        ge=1,
        le=128,
        description="Thread count for llama.cpp inference.",
    )
    max_tokens: int = Field(default=256, ge=32, le=1024)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.1, le=1.0)
    retrieval_top_k: int = Field(default=4, ge=1, le=20)
    starter_prompts: list[str] = Field(
        default_factory=lambda: [
            "帮我快速了解这个工作区现在能做什么",
            "先根据当前配置给我一个最稳妥的使用路径",
            "用最少步骤带我完成第一次任务配置",
        ],
        description="Default starter prompts shown in the welcome/onboarding UI.",
    )


_embedded_model_config = EmbeddedModelConfig()


def get_embedded_model_config() -> EmbeddedModelConfig:
    return _embedded_model_config


def load_embedded_model_config_from_dict(config_dict: dict) -> None:
    global _embedded_model_config
    _embedded_model_config = EmbeddedModelConfig(**config_dict)
