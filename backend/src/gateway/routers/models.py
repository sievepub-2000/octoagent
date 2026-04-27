from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.config import get_app_config
from src.config.app_config import AppConfig, reload_app_config
from src.config.embedded_model_config import get_embedded_model_config
from src.models.factory import EMBEDDED_BACKUP_MODEL_NAME
from src.models.interfaces import resolve_model_interface_profile
from src.models.provider_adapter import resolve_provider_adapter_profile

router = APIRouter(prefix="/api", tags=["models"])


class ModelResponse(BaseModel):
    """Response model for model information."""

    name: str = Field(..., description="Unique identifier for the model")
    display_name: str | None = Field(None, description="Human-readable name")
    description: str | None = Field(None, description="Model description")
    use: str | None = Field(None, description="Raw provider class path, if configured")
    interface_type: str | None = Field(None, description="Configured normalized model interface type")
    provider_name: str | None = Field(None, description="Configured provider/vendor label")
    resolved_interface_type: str | None = Field(None, description="Effective resolved model interface type")
    resolved_provider_family: str | None = Field(None, description="Effective normalized provider family")
    resolved_use_path: str | None = Field(None, description="Effective provider class path after interface inference")
    adapter_type: str | None = Field(None, description="Effective provider adapter type")
    adapter_request_contract: str | None = Field(None, description="Normalized upstream request contract")
    adapter_response_contract: str | None = Field(None, description="Normalized upstream response contract")
    adapter_streaming_contract: str | None = Field(None, description="Normalized upstream streaming contract")
    adapter_auth_mode: str | None = Field(None, description="Normalized authentication strategy for the adapter")
    proxy_compatible: bool = Field(default=False, description="Whether the model can use a CLI/OpenAI-style proxy contract")
    semantic_format: str | None = Field(None, description="Effective semantic message format")
    thinking_semantics: str | None = Field(None, description="How thinking mode is represented for the interface")
    supports_thinking: bool = Field(default=False, description="Whether model supports thinking mode")
    supports_reasoning_effort: bool = Field(default=False, description="Whether model supports reasoning effort")
    supports_vision: bool = Field(default=False, description="Whether model supports image inputs")
    fallback_models: list[str] = Field(
        default_factory=list,
        description="Ordered backup model names that may be used when the primary model fails.",
    )
    max_context_tokens: int | None = Field(
        default=None,
        description="Declared maximum context window, if configured.",
    )
    is_embedded_backup: bool = Field(
        default=False,
        description="Whether this model is the built-in embedded emergency backup.",
    )


class ModelsListResponse(BaseModel):
    """Response model for listing all models."""

    models: list[ModelResponse]


class DeleteModelResponse(BaseModel):
    deleted: bool = True
    model_name: str


class ModelCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    display_name: str | None = None
    description: str | None = None
    model: str = Field(..., min_length=1)
    use: str | None = None
    interface_type: str | None = None
    provider_name: str | None = None
    supports_thinking: bool = False
    supports_reasoning_effort: bool = False
    when_thinking_enabled: dict | None = None
    thinking: dict | None = None
    supports_vision: bool = False
    fallback_models: list[str] = Field(default_factory=list)
    max_context_tokens: int | None = None

    model_config = ConfigDict(extra="allow")


class ModelUpdateRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    model: str | None = None
    use: str | None = None
    interface_type: str | None = None
    provider_name: str | None = None
    supports_thinking: bool | None = None
    supports_reasoning_effort: bool | None = None
    when_thinking_enabled: dict | None = None
    thinking: dict | None = None
    supports_vision: bool | None = None
    fallback_models: list[str] | None = None
    max_context_tokens: int | None = None

    model_config = ConfigDict(extra="allow")


class FallbackPoolStatusResponse(BaseModel):
    """Read-only status for the free-tier fallback model pool."""

    enabled: bool = Field(..., description="Whether the NVIDIA free-tier fallback pool is active for the running process")
    reason: str = Field(..., description="Human-readable explanation of the current state")
    api_key_present: bool = Field(..., description="Whether NVIDIA_API_KEY / FREE_CLAUDE_CODE_API_KEY is resolvable")
    base_url: str = Field(..., description="Resolved base URL for NVIDIA NIM")
    pool_models: list[str] = Field(default_factory=list, description="Model names currently injected into the pool")
    operator_override: bool = Field(..., description="True when the operator already configured an nvidia-* entry so injection is skipped")


def _config_path() -> Path:
    return AppConfig.resolve_config_path()


def _load_config_data() -> dict:
    config_path = _config_path()
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def _write_config_data(config_data: dict) -> None:
    config_path = _config_path()
    config_path.write_text(yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    reload_app_config(str(config_path))


def _serialize_model(model) -> ModelResponse:
    resolved_interface_type = None
    adapter_profile = None
    interface_profile = None
    resolved_use_path = None
    if hasattr(model, "resolved_interface_type"):
        try:
            resolved_interface_type = model.resolved_interface_type()
        except Exception:
            resolved_interface_type = None
    if hasattr(model, "resolved_use"):
        try:
            resolved_use_path = model.resolved_use()
        except Exception:
            resolved_use_path = None
    try:
        adapter_profile = resolve_provider_adapter_profile(model)
    except Exception:
        adapter_profile = None
    try:
        interface_profile = resolve_model_interface_profile(
            interface_type=getattr(model, "interface_type", None),
            provider_name=getattr(model, "provider_name", None),
            provider_family=getattr(model, "provider_family", None),
            use_path=getattr(model, "use", None),
        )
    except Exception:
        interface_profile = None
    return ModelResponse(
        name=model.name,
        display_name=model.display_name,
        description=model.description,
        use=getattr(model, "use", None),
        interface_type=getattr(model, "interface_type", None),
        provider_name=getattr(model, "provider_name", None),
        resolved_interface_type=resolved_interface_type,
        resolved_provider_family=(adapter_profile.provider_family if adapter_profile is not None else None),
        resolved_use_path=resolved_use_path,
        adapter_type=(adapter_profile.adapter_type if adapter_profile is not None else None),
        adapter_request_contract=(adapter_profile.request_contract if adapter_profile is not None else None),
        adapter_response_contract=(adapter_profile.response_contract if adapter_profile is not None else None),
        adapter_streaming_contract=(adapter_profile.streaming_contract if adapter_profile is not None else None),
        adapter_auth_mode=(adapter_profile.auth_mode if adapter_profile is not None else None),
        proxy_compatible=(adapter_profile.proxy_compatible if adapter_profile is not None else False),
        semantic_format=(interface_profile.semantic_format if interface_profile is not None else None),
        thinking_semantics=(interface_profile.thinking_semantics if interface_profile is not None else None),
        supports_thinking=model.supports_thinking,
        supports_reasoning_effort=model.supports_reasoning_effort,
        supports_vision=model.supports_vision,
        fallback_models=model.fallback_models,
        max_context_tokens=model.max_context_tokens,
        is_embedded_backup=False,
    )


def _delete_model_from_config(model_name: str) -> bool:
    config_data = _load_config_data()
    models = list(config_data.get("models") or [])
    filtered = [model for model in models if str(model.get("name")) != model_name]
    if len(filtered) == len(models):
        return False
    config_data["models"] = filtered
    _write_config_data(config_data)
    return True


def _create_model_in_config(request: ModelCreateRequest) -> ModelResponse:
    from src.config.model_auto_inference import auto_infer_model_fields

    config_data = _load_config_data()
    models = list(config_data.get("models") or [])
    if any(str(model.get("name")) == request.name for model in models):
        raise HTTPException(status_code=409, detail=f"Model '{request.name}' already exists")
    payload = request.model_dump(exclude_none=True)
    auto_infer_model_fields(payload)
    models.append(payload)
    config_data["models"] = models
    _write_config_data(config_data)
    model_config = get_app_config().get_model_config(request.name)
    if model_config is None:
        raise HTTPException(status_code=500, detail=f"Model '{request.name}' was not available after reload")
    return _serialize_model(model_config)


def _update_model_in_config(model_name: str, request: ModelUpdateRequest) -> ModelResponse:
    from src.config.model_auto_inference import auto_infer_model_fields

    config_data = _load_config_data()
    models = list(config_data.get("models") or [])
    updated = False
    payload = request.model_dump(exclude_unset=True)
    for index, model in enumerate(models):
        if str(model.get("name")) != model_name:
            continue
        merged = {**model, **payload, "name": model_name}
        auto_infer_model_fields(merged)
        models[index] = merged
        updated = True
        break
    if not updated:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
    config_data["models"] = models
    _write_config_data(config_data)
    model_config = get_app_config().get_model_config(model_name)
    if model_config is None:
        raise HTTPException(status_code=500, detail=f"Model '{model_name}' was not available after reload")
    return _serialize_model(model_config)


@router.get(
    "/models",
    response_model=ModelsListResponse,
    summary="List All Models",
    description="Retrieve a list of all available AI models configured in the system.",
)
async def list_models() -> ModelsListResponse:
    """List all available models from configuration.

    Returns model information suitable for frontend display,
    excluding sensitive fields like API keys and internal configuration.

    Returns:
        A list of all configured models with their metadata.

    Example Response:
        ```json
        {
            "models": [
                {
                    "name": "gpt-4",
                    "display_name": "GPT-4",
                    "description": "OpenAI GPT-4 model",
                    "supports_thinking": false
                },
                {
                    "name": "claude-3-opus",
                    "display_name": "Claude 3 Opus",
                    "description": "Anthropic Claude 3 Opus model",
                    "supports_thinking": true
                }
            ]
        }
        ```
    """
    config = get_app_config()
    models = [_serialize_model(model) for model in config.models]
    embedded_config = get_embedded_model_config()
    if embedded_config.enabled:
        models.append(
            ModelResponse(
                name=EMBEDDED_BACKUP_MODEL_NAME,
                display_name="Embedded Bootstrap Backup",
                description="Built-in tiny local emergency fallback model for dialogue continuity and reconfiguration guidance.",
                resolved_use_path=None,
                resolved_provider_family="generic",
                adapter_type="generic",
                adapter_request_contract="generic.invoke",
                adapter_response_contract="generic.invoke",
                adapter_streaming_contract="generic.stream",
                adapter_auth_mode="provider_native",
                proxy_compatible=False,
                semantic_format="generic",
                thinking_semantics="none",
                supports_thinking=False,
                supports_reasoning_effort=False,
                supports_vision=False,
                fallback_models=[],
                max_context_tokens=embedded_config.n_ctx,
                is_embedded_backup=True,
            )
        )
    return ModelsListResponse(models=models)


@router.get(
    "/models/{model_name}",
    response_model=ModelResponse,
    summary="Get Model Details",
    description="Retrieve detailed information about a specific AI model by its name.",
)
async def get_model(model_name: str) -> ModelResponse:
    """Get a specific model by name.

    Args:
        model_name: The unique name of the model to retrieve.

    Returns:
        Model information if found.

    Raises:
        HTTPException: 404 if model not found.

    Example Response:
        ```json
        {
            "name": "gpt-4",
            "display_name": "GPT-4",
            "description": "OpenAI GPT-4 model",
            "supports_thinking": false
        }
        ```
    """
    config = get_app_config()
    model = config.get_model_config(model_name)
    if model_name == EMBEDDED_BACKUP_MODEL_NAME and get_embedded_model_config().enabled:
        embedded_config = get_embedded_model_config()
        return ModelResponse(
            name=EMBEDDED_BACKUP_MODEL_NAME,
            display_name="Embedded Bootstrap Backup",
            description="Built-in tiny local emergency fallback model for dialogue continuity and reconfiguration guidance.",
            resolved_use_path=None,
            resolved_provider_family="generic",
            adapter_type="generic",
            adapter_request_contract="generic.invoke",
            adapter_response_contract="generic.invoke",
            adapter_streaming_contract="generic.stream",
            adapter_auth_mode="provider_native",
            proxy_compatible=False,
            semantic_format="generic",
            thinking_semantics="none",
            supports_thinking=False,
            supports_reasoning_effort=False,
            supports_vision=False,
            fallback_models=[],
            max_context_tokens=embedded_config.n_ctx,
            is_embedded_backup=True,
        )
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

    return _serialize_model(model)


@router.post(
    "/models",
    response_model=ModelResponse,
    summary="Create Model",
    description="Create a configured AI model entry in config.yaml and reload application config.",
)
async def create_model(request: ModelCreateRequest) -> ModelResponse:
    return _create_model_in_config(request)


@router.put(
    "/models/{model_name}",
    response_model=ModelResponse,
    summary="Update Model",
    description="Update a configured AI model entry in config.yaml and reload application config.",
)
async def update_model(model_name: str, request: ModelUpdateRequest) -> ModelResponse:
    return _update_model_in_config(model_name, request)


@router.delete(
    "/models/{model_name}",
    response_model=DeleteModelResponse,
    summary="Delete Model",
    description="Delete a configured AI model from config.yaml and reload application config.",
)
async def delete_model(model_name: str) -> DeleteModelResponse:
    if model_name == EMBEDDED_BACKUP_MODEL_NAME:
        raise HTTPException(status_code=400, detail="Embedded backup model cannot be deleted")
    deleted = _delete_model_from_config(model_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
    return DeleteModelResponse(model_name=model_name)


@router.get(
    "/fallback-pool/status",
    response_model=FallbackPoolStatusResponse,
    summary="Free fallback model pool status",
    description="Observation-only status for the NVIDIA NIM free-tier fallback pool injected by free_claude_code_fallback.",
)
async def get_fallback_pool_status() -> FallbackPoolStatusResponse:
    import os as _os

    from src.config.free_claude_code_fallback import (
        _DEFAULT_BASE_URL,
        _FREE_POOL,
        _resolve_api_key,
    )

    api_key = _resolve_api_key()
    base_url = _os.environ.get("NVIDIA_BASE_URL", _DEFAULT_BASE_URL)
    pool_names = [str(t.get("name")) for t in _FREE_POOL if t.get("name")]

    # Determine operator_override from the raw config file (pre-injection).
    # config.models may contain auto-injected entries, so we must not use it
    # as the source of truth here.
    operator_has_nvidia = False
    try:
        raw_config_data = _load_config_data()
        for entry in raw_config_data.get("models") or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").lower()
            provider = str(entry.get("provider_name") or "").lower()
            if name.startswith("nvidia-") or provider == "nvidia":
                operator_has_nvidia = True
                break
    except Exception:
        operator_has_nvidia = False

    config = get_app_config()

    if not api_key:
        return FallbackPoolStatusResponse(
            enabled=False,
            reason="NVIDIA_API_KEY / FREE_CLAUDE_CODE_API_KEY not set; pool disabled.",
            api_key_present=False,
            base_url=base_url,
            pool_models=pool_names,
            operator_override=operator_has_nvidia,
        )

    if operator_has_nvidia:
        return FallbackPoolStatusResponse(
            enabled=False,
            reason="Operator configured nvidia-* model(s) in config.yaml; automatic injection skipped.",
            api_key_present=True,
            base_url=base_url,
            pool_models=pool_names,
            operator_override=True,
        )

    # API key present and no operator override → pool is active.
    injected = [
        m.name
        for m in config.models
        if (getattr(m, "name", "") or "").startswith("nvidia-")
    ]
    return FallbackPoolStatusResponse(
        enabled=True,
        reason=f"{len(injected or pool_names)} NVIDIA NIM free-tier model(s) reachable.",
        api_key_present=True,
        base_url=base_url,
        pool_models=injected or pool_names,
        operator_override=False,
    )
