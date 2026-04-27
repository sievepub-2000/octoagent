"""Semantic translation layer for model-provider differences."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from langchain.chat_models import BaseChatModel
from langchain_core.language_models.chat_models import BaseChatModel as CoreBaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable
from pydantic import ConfigDict, Field

from src.models.interfaces import resolve_model_interface_profile

ModelProviderFamily = Literal["openai", "anthropic", "google", "deepseek", "generic"]
ModelSemanticFormat = Literal["openai_chat", "anthropic", "generic"]
ThinkingSemantics = Literal["extra_body", "direct", "none"]

_LLAMACPP_TOOL_CALL_RE = re.compile(
    r"<\|(?:tool_call|call):(?P<name>[A-Za-z0-9_.:-]+)(?P<args>\{.*?\})<tool_call\|>",
    re.DOTALL,
)
_LLAMACPP_TOOL_MARKERS = (
    "<|awnsering_with_tool_call>",
    "<|answering_with_tool_call>",
    "<|thought",
    "<channel|>",
)


@dataclass(frozen=True)
class ModelSemanticProfile:
    interface_type: str = "generic"
    provider_family: ModelProviderFamily = "generic"
    content_format: ModelSemanticFormat = "generic"
    thinking_semantics: ThinkingSemantics = "none"


class ModelSemanticTranslator:
    """Normalize provider-facing settings, messages, and tool-binding inputs."""

    def build_profile(self, model_config) -> ModelSemanticProfile:
        interface_profile = resolve_model_interface_profile(
            interface_type=getattr(model_config, "interface_type", None),
            provider_name=getattr(model_config, "provider_name", None),
            provider_family=getattr(model_config, "provider_family", None),
            use_path=getattr(model_config, "use", None),
        )
        provider_family = self._infer_provider_family(
            getattr(model_config, "provider_family", None),
            getattr(model_config, "use", ""),
            interface_profile.provider_family,
        )
        content_format = self._infer_content_format(
            getattr(model_config, "semantic_format", None),
            provider_family,
            interface_profile.semantic_format,
        )
        return ModelSemanticProfile(
            interface_type=interface_profile.name,
            provider_family=provider_family,
            content_format=content_format,
            thinking_semantics=self._infer_thinking_semantics(interface_profile.name, provider_family),
        )

    def merge_thinking_config(self, model_config) -> tuple[bool, dict[str, Any]]:
        has_thinking_settings = (
            getattr(model_config, "when_thinking_enabled", None) is not None
            or getattr(model_config, "thinking", None) is not None
        )
        effective_wte: dict[str, Any] = (
            dict(model_config.when_thinking_enabled) if getattr(model_config, "when_thinking_enabled", None) else {}
        )
        thinking_shortcut = getattr(model_config, "thinking", None)
        if thinking_shortcut is not None:
            merged_thinking = {**(effective_wte.get("thinking") or {}), **thinking_shortcut}
            effective_wte = {**effective_wte, "thinking": merged_thinking}
        return has_thinking_settings, effective_wte

    def apply_runtime_semantics(
        self,
        *,
        model_config,
        profile: ModelSemanticProfile,
        thinking_enabled: bool,
        model_settings_from_config: dict[str, Any],
        runtime_kwargs: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        has_thinking_settings, effective_wte = self.merge_thinking_config(model_config)
        negotiated_settings = dict(model_settings_from_config)
        negotiated_kwargs = dict(runtime_kwargs)

        if thinking_enabled and has_thinking_settings:
            if not model_config.supports_thinking:
                raise ValueError(
                    f"Model {model_config.name} does not support thinking. "
                    "Set `supports_thinking` to true in the `config.yaml` to enable thinking."
                ) from None
            if effective_wte:
                negotiated_settings.update(effective_wte)

        if not thinking_enabled and has_thinking_settings:
            if effective_wte.get("extra_body", {}).get("thinking", {}).get("type"):
                negotiated_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
                negotiated_kwargs["reasoning_effort"] = "minimal"
            elif effective_wte.get("thinking", {}).get("type") or profile.thinking_semantics == "direct":
                negotiated_kwargs["thinking"] = {"type": "disabled"}

        if not getattr(model_config, "supports_reasoning_effort", False):
            negotiated_kwargs.pop("reasoning_effort", None)

        return negotiated_settings, negotiated_kwargs

    def normalize_messages(
        self,
        messages: list[BaseMessage],
        profile: ModelSemanticProfile,
    ) -> list[BaseMessage]:
        normalized: list[BaseMessage] = []
        for message in messages:
            content = getattr(message, "content", None)
            if not isinstance(content, list):
                normalized.append(message)
                continue
            normalized.append(
                message.model_copy(
                    update={"content": [self.normalize_content_item(item, profile) for item in content]}
                )
            )
        return normalized

    def normalize_content_item(self, item: Any, profile: ModelSemanticProfile) -> Any:
        if not isinstance(item, dict):
            return item
        item_type = str(item.get("type") or "").strip()
        if item_type in {"input_text", "text"}:
            return {"type": "text", "text": "" if item.get("text") is None else str(item.get("text"))}
        if item_type in {"input_image", "image", "image_url"}:
            image_url = self._extract_image_url(item)
            if image_url is None:
                return item
            if profile.content_format == "openai_chat":
                return {
                    "type": "image_url",
                    "image_url": image_url if isinstance(image_url, dict) else {"url": image_url},
                }
            if profile.content_format == "anthropic":
                anthropic_image = self._normalize_anthropic_image_item(image_url)
                return anthropic_image or item
        return item

    def normalize_tool_choice(self, tool_choice: Any) -> Any:
        if isinstance(tool_choice, bool):
            return "required" if tool_choice else "none"
        if tool_choice == "any":
            return "required"
        return tool_choice

    def tool_binding_kwargs(
        self,
        model: BaseChatModel,
        tools,
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not hasattr(model, "bind_tools"):
            return {}
        normalized_kwargs = dict(kwargs)
        if tool_choice is not None:
            normalized_kwargs["tool_choice"] = self.normalize_tool_choice(tool_choice)
        bound = model.bind_tools(tools, **normalized_kwargs)
        return dict(getattr(bound, "kwargs", {}))

    def _infer_provider_family(
        self,
        override: str | None,
        use_path: str,
        interface_provider_family: str,
    ) -> ModelProviderFamily:
        if interface_provider_family in {"openai", "anthropic", "google", "deepseek", "generic"}:
            inferred_from_interface = interface_provider_family
        else:
            inferred_from_interface = "generic"
        if override in {"openai", "anthropic", "google", "deepseek", "generic"}:
            return override
        if inferred_from_interface != "generic":
            return inferred_from_interface
        lowered = str(override or use_path).lower()
        if "anthropic" in lowered:
            return "anthropic"
        if "deepseek" in lowered:
            return "deepseek"
        if "google" in lowered or "gemini" in lowered:
            return "google"
        if "openai" in lowered:
            return "openai"
        return "generic"

    def _infer_content_format(
        self,
        override: str | None,
        provider_family: ModelProviderFamily,
        interface_content_format: str,
    ) -> ModelSemanticFormat:
        normalized_override = str(override or "").strip().lower()
        if normalized_override in {"openai", "openai_chat"}:
            return "openai_chat"
        if normalized_override == "anthropic":
            return "anthropic"
        if normalized_override == "generic":
            return "generic"
        if interface_content_format in {"openai_chat", "anthropic", "generic"}:
            return interface_content_format  # type: ignore[return-value]
        if provider_family in {"openai", "deepseek"}:
            return "openai_chat"
        if provider_family == "anthropic":
            return "anthropic"
        return "generic"

    def _infer_thinking_semantics(self, interface_type: str, provider_family: ModelProviderFamily) -> ThinkingSemantics:
        if interface_type == "anthropic_messages" or provider_family == "anthropic":
            return "direct"
        if interface_type in {"openai_compatible", "deepseek_reasoner"} or provider_family in {"openai", "deepseek"}:
            return "extra_body"
        return "none"

    def _extract_image_url(self, item: dict[str, Any]) -> str | dict[str, Any] | None:
        image_url = item.get("image_url")
        if isinstance(image_url, (str, dict)):
            return image_url
        url = item.get("url")
        if isinstance(url, str):
            return url
        return None

    def _normalize_anthropic_image_item(self, image_url: str | dict[str, Any]) -> dict[str, Any] | None:
        url = image_url.get("url") if isinstance(image_url, dict) else image_url
        if not isinstance(url, str) or not url.startswith("data:") or ";base64," not in url:
            return None
        header, encoded = url.split(",", 1)
        media_type = header[5:].split(";", 1)[0] or "image/png"
        return {
            "type": "image",
            "source_type": "base64",
            "media_type": media_type,
            "data": encoded,
        }


def _parse_llamacpp_tool_args(raw_args: str) -> dict[str, Any] | None:
    cleaned = raw_args.strip().replace('<|"|>', '"')
    cleaned = re.sub(r'([\{,]\s*)([A-Za-z_][A-Za-z0-9_\-]*)\s*:', r'\1"\2":', cleaned)
    try:
        parsed = json.loads(cleaned)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_llamacpp_tool_calls(content: str) -> tuple[str, list[dict[str, Any]]]:
    tool_calls: list[dict[str, Any]] = []
    if "<|tool_call:" not in content and "<|call:" not in content:
        return content, tool_calls

    stripped_content = content
    for marker in _LLAMACPP_TOOL_MARKERS:
        stripped_content = stripped_content.replace(marker, "")

    for index, match in enumerate(_LLAMACPP_TOOL_CALL_RE.finditer(content), start=1):
        args = _parse_llamacpp_tool_args(match.group("args"))
        if args is None:
            continue
        tool_calls.append(
            {
                "name": match.group("name"),
                "args": args,
                "id": f"llamacpp_call_{index}",
                "type": "tool_call",
            }
        )

    if not tool_calls:
        return content, tool_calls

    stripped_content = _LLAMACPP_TOOL_CALL_RE.sub("", stripped_content).strip()
    return stripped_content, tool_calls


def _normalize_ai_message_tool_calls(message: AIMessage) -> AIMessage:
    if message.tool_calls or not isinstance(message.content, str):
        return message
    normalized_content, tool_calls = _extract_llamacpp_tool_calls(message.content)
    if not tool_calls:
        return message
    return message.model_copy(
        update={
            "content": normalized_content,
            "tool_calls": tool_calls,
        }
    )


def _normalize_chat_result_tool_calls(result: ChatResult) -> ChatResult:
    generations = []
    changed = False
    for generation in result.generations:
        message = getattr(generation, "message", None)
        if not isinstance(message, AIMessage):
            generations.append(generation)
            continue
        normalized_message = _normalize_ai_message_tool_calls(message)
        if normalized_message is not message:
            changed = True
            generations.append(generation.model_copy(update={"message": normalized_message}))
            continue
        generations.append(generation)
    if not changed:
        return result
    return result.model_copy(update={"generations": generations})


class SemanticChatModel(CoreBaseChatModel):
    """Provider model wrapper that applies semantic normalization at call time."""

    wrapped_model: BaseChatModel
    semantic_profile: ModelSemanticProfile
    translator: ModelSemanticTranslator = Field(default_factory=ModelSemanticTranslator)
    bound_tools_list: list | None = None
    bound_tools_kwargs: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return f"semantic-{self.wrapped_model._llm_type}"

    def bind_tools(
        self,
        tools,
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        bound = self.model_copy()
        bound.bound_tools_list = tools
        bound.bound_tools_kwargs = dict(kwargs)
        if tool_choice is not None:
            bound.bound_tools_kwargs["tool_choice"] = tool_choice
        return bound

    def with_structured_output(self, schema: Any, **kwargs: Any):
        if not hasattr(self.wrapped_model, "with_structured_output"):
            raise NotImplementedError("Wrapped model does not support structured output")
        return self.wrapped_model.with_structured_output(schema, **kwargs)

    def bound_invocation_kwargs(self) -> dict[str, Any]:
        if self.bound_tools_list is None:
            return {}
        tool_kwargs = dict(self.bound_tools_kwargs)
        tool_choice = tool_kwargs.pop("tool_choice", None)
        return self.translator.tool_binding_kwargs(
            self.wrapped_model,
            self.bound_tools_list,
            tool_choice=tool_choice,
            **tool_kwargs,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        normalized_messages = self.translator.normalize_messages(messages, self.semantic_profile)
        merged = {**kwargs, **self.bound_invocation_kwargs()}
        result = self.wrapped_model._generate(normalized_messages, stop=stop, run_manager=run_manager, **merged)
        return _normalize_chat_result_tool_calls(result)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        normalized_messages = self.translator.normalize_messages(messages, self.semantic_profile)
        merged = {**kwargs, **self.bound_invocation_kwargs()}
        result = await self.wrapped_model._agenerate(normalized_messages, stop=stop, run_manager=run_manager, **merged)
        return _normalize_chat_result_tool_calls(result)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ):
        normalized_messages = self.translator.normalize_messages(messages, self.semantic_profile)
        merged = {**kwargs, **self.bound_invocation_kwargs()}
        yield from self.wrapped_model._stream(normalized_messages, stop=stop, run_manager=run_manager, **merged)

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ):
        normalized_messages = self.translator.normalize_messages(messages, self.semantic_profile)
        merged = {**kwargs, **self.bound_invocation_kwargs()}
        async for chunk in self.wrapped_model._astream(normalized_messages, stop=stop, run_manager=run_manager, **merged):
            yield chunk
