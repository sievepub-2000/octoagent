"""Normalized model interface registry for broad provider compatibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ModelInterfaceType = Literal[
    "openai_compatible",
    "anthropic_messages",
    "google_genai",
    "deepseek_reasoner",
    "generic",
]


@dataclass(frozen=True)
class ModelInterfaceProfile:
    name: ModelInterfaceType
    default_use: str | None
    provider_family: str
    semantic_format: str
    thinking_semantics: str
    aliases: tuple[str, ...] = ()


_INTERFACE_PROFILES: dict[ModelInterfaceType, ModelInterfaceProfile] = {
    "openai_compatible": ModelInterfaceProfile(
        name="openai_compatible",
        default_use="langchain_openai:ChatOpenAI",
        provider_family="openai",
        semantic_format="openai_chat",
        thinking_semantics="extra_body",
        aliases=(
            "openai-compatible",
            "cli-proxy-api",
            "cli_proxy_api",
            "copilot_cli_proxy",
            "openai",
            "azure_openai",
            "openrouter",
            "groq",
            "together",
            "fireworks",
            "mistral",
            "xai",
            "sambanova",
            "deepinfra",
            "perplexity",
            "novita",
            "huggingface",
            "huggingface_router",
            "ollama",
            "vllm",
            "llamacpp",
            "openclaw",
            "local",
        ),
    ),
    "anthropic_messages": ModelInterfaceProfile(
        name="anthropic_messages",
        default_use="langchain_anthropic:ChatAnthropic",
        provider_family="anthropic",
        semantic_format="anthropic",
        thinking_semantics="direct",
        aliases=("anthropic-messages", "anthropic", "claude"),
    ),
    "google_genai": ModelInterfaceProfile(
        name="google_genai",
        default_use="langchain_google_genai:ChatGoogleGenerativeAI",
        provider_family="google",
        semantic_format="generic",
        thinking_semantics="none",
        aliases=("google-genai", "google", "gemini"),
    ),
    "deepseek_reasoner": ModelInterfaceProfile(
        name="deepseek_reasoner",
        default_use="src.models.patched_deepseek:PatchedChatDeepSeek",
        provider_family="deepseek",
        semantic_format="openai_chat",
        thinking_semantics="extra_body",
        aliases=(
            "deepseek-reasoner",
            "deepseek",
            "moonshot",
            "kimi",
            "volcengine",
            "doubao",
        ),
    ),
    "generic": ModelInterfaceProfile(
        name="generic",
        default_use=None,
        provider_family="generic",
        semantic_format="generic",
        thinking_semantics="none",
        aliases=("custom", "generic"),
    ),
}


def _normalize_key(value: str | None) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_interface_type(value: str | None) -> ModelInterfaceType | None:
    normalized = _normalize_key(value)
    if not normalized:
        return None
    for interface_type, profile in _INTERFACE_PROFILES.items():
        if normalized == interface_type or normalized in {_normalize_key(alias) for alias in profile.aliases}:
            return interface_type
    return None


def resolve_model_interface_profile(
    *,
    interface_type: str | None = None,
    provider_name: str | None = None,
    provider_family: str | None = None,
    use_path: str | None = None,
) -> ModelInterfaceProfile:
    for candidate in (interface_type, provider_name, provider_family, use_path):
        resolved_type = normalize_interface_type(candidate)
        if resolved_type is not None:
            return _INTERFACE_PROFILES[resolved_type]

    lowered_use = _normalize_key(use_path)
    if "anthropic" in lowered_use:
        return _INTERFACE_PROFILES["anthropic_messages"]
    if "deepseek" in lowered_use:
        return _INTERFACE_PROFILES["deepseek_reasoner"]
    if "google" in lowered_use or "gemini" in lowered_use:
        return _INTERFACE_PROFILES["google_genai"]
    if "openai" in lowered_use:
        return _INTERFACE_PROFILES["openai_compatible"]
    return _INTERFACE_PROFILES["generic"]