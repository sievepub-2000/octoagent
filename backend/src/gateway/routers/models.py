import asyncio
import json
import os
import re
import tempfile
import time
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.models.interfaces import normalize_interface_type, resolve_model_interface_profile
from src.models.provider_adapter import resolve_provider_adapter_profile
from src.runtime.config import get_app_config
from src.runtime.config.app_config import AppConfig, reload_app_config
from src.runtime.config.paths import get_setup_state_file

router = APIRouter(prefix="/api", tags=["models"])
_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MANAGED_SECRET_PREFIX = "OCTOAGENT_MODEL_"
_SENSITIVE_MODEL_KEYS = {
    "api_key",
    "apikey",
    "apiKey",
    "google_api_key",
    "openai_api_key",
    "anthropic_api_key",
    "client_secret",
}


class ModelResponse(BaseModel):
    """Response model for model information."""

    name: str = Field(..., description="Unique identifier for the model")
    display_name: str | None = Field(None, description="Human-readable name")
    description: str | None = Field(None, description="Model description")
    model: str | None = Field(None, description="Provider model identifier")
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
    is_default: bool = Field(default=False, description="Whether this is the default model")


class ModelsListResponse(BaseModel):
    """Response model for listing all models."""

    models: list[ModelResponse]


class DeleteModelResponse(BaseModel):
    deleted: bool = True
    model_name: str


class ModelConnectionTestResponse(BaseModel):
    ok: bool
    model_name: str
    latency_ms: int
    response_preview: str


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


def _config_path() -> Path:
    return AppConfig.resolve_config_path()


def _load_config_data() -> dict:
    config_path = _config_path()
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def _write_config_data(config_data: dict) -> None:
    config_path = _config_path()
    serialized = yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(config_path.parent),
        prefix=f".{config_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(serialized)
        temp_path = Path(handle.name)
    os.replace(temp_path, config_path)
    reload_app_config(str(config_path))


def _project_dotenv_path() -> Path:
    if managed_path := os.getenv("OCTOAGENT_MANAGED_SECRETS_FILE", "").strip():
        return Path(managed_path).expanduser().resolve()
    config_path = _config_path().resolve()
    # Standard layout: <repo>/runtime/config/config.yaml. Root-level packaged
    # configs (for example /app/config.yaml in Docker) use their own directory.
    if config_path.parent.name == "config" and config_path.parent.parent.name == "runtime":
        return config_path.parents[2] / ".env"
    return config_path.parent / ".env"


def _managed_secret_name(model_name: str, key: str) -> str:
    model_token = re.sub(r"[^A-Za-z0-9]+", "_", model_name).strip("_").upper()
    key_token = re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_").upper()
    return f"{_MANAGED_SECRET_PREFIX}{model_token}_{key_token}"


def _persist_dotenv_secret(env_name: str, secret: str) -> None:
    dotenv_path = _project_dotenv_path()
    lines = dotenv_path.read_text(encoding="utf-8").splitlines() if dotenv_path.exists() else []
    assignment = f"{env_name}={secret}"
    prefix = f"{env_name}="
    updated = False
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = assignment
            updated = True
            break
    if not updated:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(assignment)
    dotenv_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(dotenv_path.parent),
        prefix=".env.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write("\n".join(lines) + "\n")
        temp_path = Path(handle.name)
    try:
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, dotenv_path)
        os.chmod(dotenv_path, 0o600)
    finally:
        temp_path.unlink(missing_ok=True)
    os.environ[env_name] = secret


def _remove_managed_dotenv_secrets(env_names: set[str]) -> None:
    if not env_names:
        return
    dotenv_path = _project_dotenv_path()
    if dotenv_path.exists():
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
        filtered = [line for line in lines if not any(line.startswith(f"{name}=") for name in env_names)]
        dotenv_path.write_text("\n".join(filtered) + "\n", encoding="utf-8")
        os.chmod(dotenv_path, 0o600)
    for name in env_names:
        os.environ.pop(name, None)


def _normalize_model_payload(
    payload: dict,
    *,
    existing_model_names: set[str],
    current_name: str | None = None,
) -> dict:
    normalized = {key: value for key, value in payload.items() if value is not None and not (isinstance(value, str) and value.strip() == "")}

    name = str(normalized.get("name") or current_name or "").strip()
    if not _MODEL_NAME_RE.fullmatch(name):
        raise HTTPException(
            status_code=400,
            detail="Model name must start with a letter or number and contain only letters, numbers, dot, underscore, colon, or hyphen.",
        )
    normalized["name"] = name

    provider_model = str(normalized.get("model") or "").strip()
    if not provider_model:
        raise HTTPException(status_code=400, detail="Provider model id is required")
    normalized["model"] = provider_model

    interface_type = normalized.get("interface_type")
    if interface_type:
        resolved_interface = normalize_interface_type(str(interface_type))
        if resolved_interface is None:
            raise HTTPException(status_code=400, detail=f"Unsupported interface_type '{interface_type}'")
        normalized["interface_type"] = resolved_interface

    if "fallback_models" in normalized:
        fallback_models = []
        for item in normalized.get("fallback_models") or []:
            fallback_name = str(item).strip()
            if not fallback_name or fallback_name == name:
                continue
            if fallback_name not in existing_model_names:
                raise HTTPException(status_code=400, detail=f"Fallback model '{fallback_name}' is not configured")
            fallback_models.append(fallback_name)
        normalized["fallback_models"] = list(dict.fromkeys(fallback_models))

    max_context_tokens = normalized.get("max_context_tokens")
    if max_context_tokens is not None:
        try:
            max_context_tokens_int = int(max_context_tokens)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="max_context_tokens must be a positive integer") from exc
        if max_context_tokens_int <= 0:
            raise HTTPException(status_code=400, detail="max_context_tokens must be a positive integer")
        normalized["max_context_tokens"] = max_context_tokens_int

    for key, value in list(normalized.items()):
        if key not in _SENSITIVE_MODEL_KEYS:
            continue
        secret_ref = str(value).strip()
        if not secret_ref:
            normalized.pop(key, None)
            continue
        if secret_ref.lower() == "none":
            normalized[key] = "none"
            continue
        if secret_ref.startswith("$"):
            env_name = secret_ref[1:]
            if not _ENV_NAME_RE.fullmatch(env_name):
                raise HTTPException(status_code=400, detail=f"{key} contains an invalid environment variable reference")
            normalized[key] = secret_ref
            continue
        if "\n" in secret_ref or "\r" in secret_ref:
            raise HTTPException(status_code=400, detail=f"{key} cannot contain line breaks")
        env_name = _managed_secret_name(name, key)
        _persist_dotenv_secret(env_name, secret_ref)
        normalized[key] = "$" + env_name

    if normalized.get("interface_type") == "google_genai" and "api_key" in normalized and "google_api_key" not in normalized:
        normalized["google_api_key"] = normalized.pop("api_key")

    return normalized


def _clean_deleted_model_references(config_data: dict, deleted_model_name: str) -> None:
    for model in config_data.get("models") or []:
        if not isinstance(model, dict):
            continue
        fallbacks = [str(item) for item in model.get("fallback_models") or [] if str(item) != deleted_model_name]
        model["fallback_models"] = list(dict.fromkeys(fallbacks))


def _repair_setup_default_model(deleted_model_name: str, remaining_models: list[dict]) -> None:
    setup_state_file = get_setup_state_file()
    if not setup_state_file.exists():
        return
    try:
        state = json.loads(setup_state_file.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(state, dict) or state.get("default_model") != deleted_model_name:
        return
    replacement = next(
        (str(model.get("name")) for model in remaining_models if isinstance(model, dict) and model.get("name")),
        "",
    )
    if replacement:
        state["default_model"] = replacement
    else:
        state.pop("default_model", None)
    setup_state_file.parent.mkdir(parents=True, exist_ok=True)
    setup_state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _serialize_model(model, *, default_model_name: str | None = None) -> ModelResponse:
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
        model=getattr(model, "model", None),
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
        is_default=model.name == default_model_name,
    )


def _set_default_model_in_config(model_name: str) -> ModelResponse:
    config_data = _load_config_data()
    models = list(config_data.get("models") or [])
    if not any(str(model.get("name")) == model_name for model in models if isinstance(model, dict)):
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
    system = config_data.setdefault("system", {})
    if not isinstance(system, dict):
        system = {}
        config_data["system"] = system
    system["default_model"] = model_name
    _write_config_data(config_data)
    model_config = get_app_config().get_model_config(model_name)
    if model_config is None:
        raise HTTPException(status_code=500, detail=f"Model '{model_name}' was not available after reload")
    return _serialize_model(model_config, default_model_name=model_name)


def _delete_model_from_config(model_name: str) -> bool:
    config_data = _load_config_data()
    models = list(config_data.get("models") or [])
    removed = next((model for model in models if str(model.get("name")) == model_name), None)
    filtered = [model for model in models if str(model.get("name")) != model_name]
    if len(filtered) == len(models):
        return False
    config_data["models"] = filtered
    _clean_deleted_model_references(config_data, model_name)
    system = config_data.get("system")
    if isinstance(system, dict) and system.get("default_model") == model_name:
        replacement = next((str(model.get("name")) for model in filtered if isinstance(model, dict) and model.get("name")), "")
        if replacement:
            system["default_model"] = replacement
        else:
            system.pop("default_model", None)
    _write_config_data(config_data)
    if isinstance(removed, dict):
        managed_env_names = {str(value)[1:] for key, value in removed.items() if key in _SENSITIVE_MODEL_KEYS and isinstance(value, str) and value.startswith("$" + _MANAGED_SECRET_PREFIX)}
        _remove_managed_dotenv_secrets(managed_env_names)
    _repair_setup_default_model(model_name, filtered)
    return True


def _create_model_in_config(request: ModelCreateRequest) -> ModelResponse:
    from src.runtime.config.model_auto_inference import auto_infer_model_fields

    config_data = _load_config_data()
    models = list(config_data.get("models") or [])
    if any(str(model.get("name")) == request.name for model in models):
        raise HTTPException(status_code=409, detail=f"Model '{request.name}' already exists")
    payload = _normalize_model_payload(
        request.model_dump(exclude_none=True),
        existing_model_names={str(model.get("name")) for model in models if isinstance(model, dict)},
    )
    auto_infer_model_fields(payload)
    models.append(payload)
    config_data["models"] = models
    _write_config_data(config_data)
    model_config = get_app_config().get_model_config(request.name)
    if model_config is None:
        raise HTTPException(status_code=500, detail=f"Model '{request.name}' was not available after reload")
    return _serialize_model(model_config)


def _update_model_in_config(model_name: str, request: ModelUpdateRequest) -> ModelResponse:
    from src.runtime.config.model_auto_inference import auto_infer_model_fields

    config_data = _load_config_data()
    models = list(config_data.get("models") or [])
    updated = False
    payload = request.model_dump(exclude_unset=True)
    for index, model in enumerate(models):
        if str(model.get("name")) != model_name:
            continue
        existing_names = {str(item.get("name")) for item in models if isinstance(item, dict)}
        merged = _normalize_model_payload(
            {**model, **payload, "name": model_name},
            existing_model_names=existing_names,
            current_name=model_name,
        )
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
    from src.runtime.config.paths import resolve_configured_default_model_name

    default_model_name = resolve_configured_default_model_name(model.name for model in config.models)
    models = [_serialize_model(model, default_model_name=default_model_name) for model in config.models]
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
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

    return _serialize_model(model)


@router.put(
    "/models/{model_name}/default",
    response_model=ModelResponse,
    summary="Set Default Model",
    description="Set an existing configured model as the system default.",
)
async def set_default_model(model_name: str) -> ModelResponse:
    return await asyncio.to_thread(_set_default_model_in_config, model_name)


@router.post(
    "/models/{model_name}/test",
    response_model=ModelConnectionTestResponse,
    summary="Test Model Connection",
    description="Send a short prompt through the configured model adapter and report real latency.",
)
async def test_model_connection(model_name: str) -> ModelConnectionTestResponse:
    from src.models import create_chat_model

    if get_app_config().get_model_config(model_name) is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            create_chat_model(name=model_name, thinking_enabled=False).ainvoke("Reply with exactly: OK"),
            timeout=60,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Model connection test timed out after 60 seconds") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Model connection test failed: {exc}") from exc
    content = getattr(response, "content", response)
    preview = content if isinstance(content, str) else str(content)
    return ModelConnectionTestResponse(
        ok=True,
        model_name=model_name,
        latency_ms=round((time.perf_counter() - started) * 1000),
        response_preview=preview[:240],
    )


@router.post(
    "/models",
    response_model=ModelResponse,
    summary="Create Model",
    description="Create a configured AI model entry in config.yaml and reload application config.",
)
async def create_model(request: ModelCreateRequest) -> ModelResponse:
    return await asyncio.to_thread(_create_model_in_config, request)


@router.put(
    "/models/{model_name}",
    response_model=ModelResponse,
    summary="Update Model",
    description="Update a configured AI model entry in config.yaml and reload application config.",
)
async def update_model(model_name: str, request: ModelUpdateRequest) -> ModelResponse:
    return await asyncio.to_thread(_update_model_in_config, model_name, request)


@router.delete(
    "/models/{model_name}",
    response_model=DeleteModelResponse,
    summary="Delete Model",
    description="Delete a configured AI model from config.yaml and reload application config.",
)
async def delete_model(model_name: str) -> DeleteModelResponse:
    deleted = await asyncio.to_thread(_delete_model_from_config, model_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
    return DeleteModelResponse(model_name=model_name)
