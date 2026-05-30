"""Semantic translation layer for model-provider differences."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from langchain.chat_models import BaseChatModel
from langchain_core.language_models.chat_models import BaseChatModel as CoreBaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
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
_XMLISH_TOOL_CALL_RE = re.compile(
    r"<tool_call\b[^>]*>\s*<function=(?P<name>[A-Za-z0-9_.:-]+)>\s*(?P<body>.*?)\s*</function>\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)
_XMLISH_TOOL_PARAMETER_RE = re.compile(
    r"<parameter=(?P<name>[A-Za-z0-9_.:-]+)>\s*(?P<value>.*?)\s*</parameter>",
    re.DOTALL | re.IGNORECASE,
)
_ORPHAN_XMLISH_FUNCTION_RE = re.compile(
    r"<function=(?P<name>[A-Za-z0-9_.:-]+)>\s*(?P<body>.*?)\s*</function>\s*(?:</tool_call>)?",
    re.DOTALL | re.IGNORECASE,
)
_BARE_XML_TOOL_RE = re.compile(
    r"<(?P<name>[A-Za-z_][A-Za-z0-9_.:-]*)\b[^>]*>\s*(?P<body>.*?)\s*</(?P=name)>",
    re.DOTALL | re.IGNORECASE,
)
_BARE_XML_ARG_RE = re.compile(
    r"<(?P<name>[A-Za-z_][A-Za-z0-9_.:-]*)\b[^>]*>\s*(?P<value>.*?)\s*</(?P=name)>",
    re.DOTALL | re.IGNORECASE,
)
_BARE_XML_FALLBACK_TOOL_NAMES = {
    "bash",
    "ls",
    "read_file",
    "write_file",
    "str_replace",
    "web_search",
    "web_fetch",
    "read_webpage",
    "convert_document",
}
_DESCRIPTION_REQUIRED_TOOL_NAMES = {"bash", "ls", "read_file", "write_file", "str_replace"}
_TAGGED_JSON_TOOL_CALL_RE = re.compile(
    r"<tool_calls?\b[^>]*>\s*(?P<body>.*?)\s*</tool_calls?>",
    re.DOTALL | re.IGNORECASE,
)
_FENCED_JSON_RE = re.compile(
    r"```(?:json|tool_code|tool_call|tool_calls)?\s*(?P<body>.*?)\s*```",
    re.DOTALL | re.IGNORECASE,
)
_TOOL_CODE_RE = re.compile(
    r"(?:<\|tool_code\|>|<tool_code\b[^>]*>|```tool_code\s*)(?P<body>.*?)(?:<\|tool_code\|>|</tool_code>|```)",
    re.DOTALL | re.IGNORECASE,
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
        has_thinking_settings = getattr(model_config, "when_thinking_enabled", None) is not None or getattr(model_config, "thinking", None) is not None
        effective_wte: dict[str, Any] = dict(model_config.when_thinking_enabled) if getattr(model_config, "when_thinking_enabled", None) else {}
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
                raise ValueError(f"Model {model_config.name} does not support thinking. Set `supports_thinking` to true in the `config.yaml` to enable thinking.") from None
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
            normalized.append(message.model_copy(update={"content": [self.normalize_content_item(item, profile) for item in content]}))
        return self._normalize_system_message_order(normalized)

    def _normalize_system_message_order(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        system_messages = [message for message in messages if getattr(message, "type", None) == "system"]
        if not system_messages:
            return self._finalize_provider_messages(messages)
        if len(system_messages) == 1 and messages and getattr(messages[0], "type", None) == "system":
            return self._finalize_provider_messages(messages)

        non_system_messages = [message for message in messages if getattr(message, "type", None) != "system"]
        merged_content = "\n\n".join(text for text in (self._system_content_text(getattr(message, "content", "")) for message in system_messages) if text)
        merged_system = system_messages[0].model_copy(update={"content": merged_content}) if isinstance(system_messages[0], SystemMessage) else SystemMessage(content=merged_content)
        return self._finalize_provider_messages([merged_system, *non_system_messages])

    def _finalize_provider_messages(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        return self._ensure_safe_assistant_tail(self._ensure_human_message(messages))

    def _ensure_human_message(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        if any(getattr(message, "type", None) == "human" for message in messages):
            return messages
        return [
            *messages,
            HumanMessage(
                content=("Continue the current task using the visible conversation context. No explicit user message was present in the provider-facing payload; if the task cannot be inferred, state the missing context instead of failing.")
            ),
        ]

    def _ensure_safe_assistant_tail(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        trailing_assistant_count = 0
        for message in reversed(messages):
            if getattr(message, "type", None) != "ai":
                break
            trailing_assistant_count += 1
        if trailing_assistant_count < 2:
            return messages
        return [
            *messages,
            HumanMessage(
                content=(
                    "Continue the latest unfinished task. The provider-facing history ended with multiple "
                    "assistant messages, so this synthetic user turn is inserted only to keep the message "
                    "contract valid. Do not repeat prior runtime error text; continue from the visible context."
                )
            ),
        ]

    def _system_content_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                else:
                    parts.append(json.dumps(item, ensure_ascii=False, default=str))
            return "\n".join(part.strip() for part in parts if part and part.strip())
        if content is None:
            return ""
        return str(content).strip()

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
    cleaned = re.sub(r"([\{,]\s*)([A-Za-z_][A-Za-z0-9_\-]*)\s*:", r'\1"\2":', cleaned)
    try:
        parsed = json.loads(cleaned)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_json_payload(text: str) -> Any | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char not in "[{":
            continue
        try:
            payload, _end = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        return payload
    return None


def _parse_json_document(text: str) -> tuple[Any, int] | None:
    cleaned = text.strip()
    if not cleaned or cleaned[0] not in "[{":
        return None
    decoder = json.JSONDecoder()
    try:
        payload, end = decoder.raw_decode(cleaned)
    except json.JSONDecodeError:
        return None
    if cleaned[end:].strip():
        return None
    return payload, len(text) - len(text.lstrip()) + end


def _parse_trailing_json_payload(text: str) -> tuple[str, Any] | None:
    stripped = text.rstrip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char not in "[{":
            continue
        try:
            payload, end = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if index + end == len(stripped):
            return stripped[:index], payload
    return None


def _payload_has_tool_call_shape(payload: Any) -> bool:
    if isinstance(payload, list):
        return any(_payload_has_tool_call_shape(item) for item in payload)
    if not isinstance(payload, dict):
        return False
    if isinstance(payload.get("tool_calls"), list) or isinstance(payload.get("tools"), list) or isinstance(payload.get("calls"), list):
        return True
    if isinstance(payload.get("function"), dict):
        return True
    name_keys = {"name", "tool", "tool_name", "function_name"}
    args_keys = {"arguments", "args", "input", "parameters"}
    return bool(name_keys.intersection(payload)) and bool(args_keys.intersection(payload))


def _coerce_tool_args(value: Any) -> dict[str, Any] | None:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = _parse_json_payload(value)
        if isinstance(parsed, dict):
            return parsed
        if parsed is None and value.strip():
            return {"input": value.strip()}
    return None


def _tool_call_id(prefix: str, index: int, raw: Any) -> str:
    digest = hashlib.sha1(json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_call_{index}_{digest}"


def _normalise_one_tool_call(raw: Any, index: int, *, prefix: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    if isinstance(raw.get("function"), dict):
        function = raw["function"]
        name = function.get("name") or raw.get("name")
        args = _coerce_tool_args(function.get("arguments") or function.get("args") or function.get("parameters"))
    else:
        name = raw.get("name") or raw.get("tool") or raw.get("tool_name") or raw.get("function_name")
        args = _coerce_tool_args(raw.get("arguments") if "arguments" in raw else raw.get("args") if "args" in raw else raw.get("input") if "input" in raw else raw.get("parameters"))

    if not isinstance(name, str) or not name.strip() or args is None:
        return None
    call_id = raw.get("id")
    if not isinstance(call_id, str) or not call_id.strip():
        call_id = _tool_call_id(prefix, index, raw)
    return {
        "name": name.strip(),
        "args": args,
        "id": call_id,
        "type": "tool_call",
    }


def _normalise_tool_call_payload(payload: Any, *, prefix: str) -> list[dict[str, Any]]:
    candidates: list[Any]
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("tool_calls"), list):
            candidates = payload["tool_calls"]
        elif isinstance(payload.get("tools"), list):
            candidates = payload["tools"]
        elif isinstance(payload.get("calls"), list):
            candidates = payload["calls"]
        else:
            candidates = [payload]
    else:
        return []

    tool_calls: list[dict[str, Any]] = []
    for index, item in enumerate(candidates, start=1):
        normalised = _normalise_one_tool_call(item, index, prefix=prefix)
        if normalised is not None:
            tool_calls.append(normalised)
    return tool_calls


def _filter_tool_calls_by_name(tool_calls: list[dict[str, Any]], allowed_tool_names: set[str] | None) -> list[dict[str, Any]]:
    if allowed_tool_names is None:
        return tool_calls
    return [call for call in tool_calls if call.get("name") in allowed_tool_names]


def _bound_tool_names(tools: list | None) -> set[str] | None:
    if tools is None:
        return None
    names: set[str] = set()
    for tool in tools:
        name = getattr(tool, "name", None)
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
            continue
        if isinstance(tool, dict):
            dict_name = tool.get("name")
            if isinstance(dict_name, str) and dict_name.strip():
                names.add(dict_name.strip())
                continue
            function = tool.get("function")
            if isinstance(function, dict) and isinstance(function.get("name"), str) and function["name"].strip():
                names.add(function["name"].strip())
    return names


def _invocation_tool_names(bound_tools: list | None, invocation_kwargs: dict[str, Any]) -> set[str] | None:
    names = _bound_tool_names(bound_tools)
    if names is not None:
        return names
    raw_tools = invocation_kwargs.get("tools")
    if isinstance(raw_tools, list):
        return _bound_tool_names(raw_tools)
    return None


def _literal_value(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        if isinstance(node, ast.Name):
            return node.id
        return ast.unparse(node) if hasattr(ast, "unparse") else None


def _normalise_ast_call(node: ast.AST, index: int) -> dict[str, Any] | None:
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        name = node.func.id
    elif isinstance(node.func, ast.Attribute):
        name = node.func.attr
    else:
        return None
    args: dict[str, Any] = {}
    for position, arg in enumerate(node.args, start=1):
        args[f"arg{position}"] = _literal_value(arg)
    for keyword in node.keywords:
        if keyword.arg is None:
            value = _literal_value(keyword.value)
            if isinstance(value, dict):
                args.update(value)
            continue
        args[keyword.arg] = _literal_value(keyword.value)
    return {
        "name": name,
        "args": args,
        "id": _tool_call_id("toolcode", index, {"name": name, "args": args}),
        "type": "tool_call",
    }


def _parse_tool_code_calls(body: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    candidates = [line.strip() for line in re.split(r"[\n;]+", body) if line.strip()]
    if not candidates and body.strip():
        candidates = [body.strip()]
    for candidate in candidates:
        try:
            parsed = ast.parse(candidate, mode="eval")
        except SyntaxError:
            try:
                parsed_module = ast.parse(candidate, mode="exec")
            except SyntaxError:
                continue
            expr_nodes = [node.value for node in parsed_module.body if isinstance(node, ast.Expr)]
        else:
            expr_nodes = [parsed.body]
        for node in expr_nodes:
            normalised = _normalise_ast_call(node, len(calls) + 1)
            if normalised is not None:
                calls.append(normalised)
    return calls


def _extract_additional_kwargs_tool_calls(message: AIMessage) -> list[dict[str, Any]]:
    additional = getattr(message, "additional_kwargs", None) or {}
    if not isinstance(additional, dict):
        return []
    if isinstance(additional.get("tool_calls"), list):
        return _normalise_tool_call_payload(additional["tool_calls"], prefix="raw")
    function_call = additional.get("function_call")
    if isinstance(function_call, dict):
        return _normalise_tool_call_payload(function_call, prefix="function")
    return []


def _extract_content_block_tool_calls(content: list[Any]) -> tuple[list[Any], list[dict[str, Any]]]:
    kept: list[Any] = []
    tool_calls: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        item_type = str(item.get("type") or "").lower()
        if item_type in {"tool_use", "tool_call", "function_call"}:
            normalised = _normalise_one_tool_call(
                {
                    "id": item.get("id"),
                    "name": item.get("name") or item.get("tool_name") or item.get("function_name"),
                    "args": item.get("input") if "input" in item else item.get("args") if "args" in item else item.get("arguments"),
                },
                len(tool_calls) + 1,
                prefix="block",
            )
            if normalised is not None:
                tool_calls.append(normalised)
                continue
        kept.append(item)
    return kept, tool_calls


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


def _extract_xmlish_tool_calls(content: str) -> tuple[str, list[dict[str, Any]]]:
    tool_calls: list[dict[str, Any]] = []
    if "<tool_call" not in content.lower() or "<function=" not in content.lower():
        return content, tool_calls

    for index, match in enumerate(_XMLISH_TOOL_CALL_RE.finditer(content), start=1):
        args: dict[str, Any] = {}
        for param in _XMLISH_TOOL_PARAMETER_RE.finditer(match.group("body")):
            args[param.group("name")] = param.group("value").strip()
        if not args:
            continue
        digest = hashlib.sha1(match.group(0).encode("utf-8")).hexdigest()[:12]
        tool_calls.append(
            {
                "name": match.group("name"),
                "args": args,
                "id": f"xmlish_call_{index}_{digest}",
                "type": "tool_call",
            }
        )

    if not tool_calls:
        return content, tool_calls

    return _XMLISH_TOOL_CALL_RE.sub("", content).strip(), tool_calls


def _extract_orphan_xmlish_function_calls(content: str) -> tuple[str, list[dict[str, Any]]]:
    tool_calls: list[dict[str, Any]] = []
    if "<function=" not in content.lower():
        return content, tool_calls

    for index, match in enumerate(_ORPHAN_XMLISH_FUNCTION_RE.finditer(content), start=1):
        args: dict[str, Any] = {}
        for param in _XMLISH_TOOL_PARAMETER_RE.finditer(match.group("body")):
            args[param.group("name")] = param.group("value").strip()
        if not args:
            continue
        digest = hashlib.sha1(match.group(0).encode("utf-8")).hexdigest()[:12]
        tool_calls.append(
            {
                "name": match.group("name"),
                "args": args,
                "id": f"orphan_xmlish_call_{index}_{digest}",
                "type": "tool_call",
            }
        )

    if not tool_calls:
        return content, tool_calls

    stripped = _ORPHAN_XMLISH_FUNCTION_RE.sub("", content).strip()
    stripped = re.sub(r"^\s*</think>\s*", "", stripped, flags=re.IGNORECASE).strip()
    return stripped, tool_calls


def _extract_bare_xml_tool_calls(
    content: str,
    *,
    allowed_tool_names: set[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    candidate_names = allowed_tool_names or _BARE_XML_FALLBACK_TOOL_NAMES
    if not candidate_names or "<" not in content:
        return content, []

    tool_calls: list[dict[str, Any]] = []
    consumed_spans: list[tuple[int, int]] = []
    lowered_candidates = {name.lower(): name for name in candidate_names}
    for match in _BARE_XML_TOOL_RE.finditer(content):
        raw_name = match.group("name")
        canonical_name = lowered_candidates.get(raw_name.lower())
        if canonical_name is None:
            continue
        args: dict[str, Any] = {}
        for arg_match in _BARE_XML_ARG_RE.finditer(match.group("body")):
            arg_name = arg_match.group("name")
            if arg_name.lower() == raw_name.lower():
                continue
            args[arg_name] = arg_match.group("value").strip()
        if not args:
            continue
        if canonical_name in _DESCRIPTION_REQUIRED_TOOL_NAMES and "description" not in args:
            args["description"] = f"Execute {canonical_name} for the requested task."
        digest = hashlib.sha1(match.group(0).encode("utf-8")).hexdigest()[:12]
        tool_calls.append(
            {
                "name": canonical_name,
                "args": args,
                "id": f"barexml_call_{len(tool_calls) + 1}_{digest}",
                "type": "tool_call",
            }
        )
        consumed_spans.append(match.span())

    if not tool_calls:
        return content, []

    stripped_parts: list[str] = []
    cursor = 0
    for start, end in consumed_spans:
        stripped_parts.append(content[cursor:start])
        cursor = end
    stripped_parts.append(content[cursor:])
    return "".join(stripped_parts).strip(), tool_calls


def _extract_jsonish_tool_calls(content: str, *, allowed_tool_names: set[str] | None = None) -> tuple[str, list[dict[str, Any]]]:
    tool_calls: list[dict[str, Any]] = []
    stripped_content = content

    def _consume(match: re.Match[str]) -> str:
        payload = _parse_json_payload(match.group("body"))
        if payload is not None:
            tool_calls.extend(_normalise_tool_call_payload(payload, prefix="json"))
            return ""
        return match.group(0)

    stripped_content = _TAGGED_JSON_TOOL_CALL_RE.sub(_consume, stripped_content)
    stripped_content = _FENCED_JSON_RE.sub(_consume, stripped_content)

    if not tool_calls:
        parsed_document = _parse_json_document(content)
        if parsed_document is not None:
            payload, _end = parsed_document
            parsed_calls = _normalise_tool_call_payload(payload, prefix="json") if _payload_has_tool_call_shape(payload) else []
            if parsed_calls:
                tool_calls.extend(parsed_calls)
                stripped_content = ""

    if not tool_calls:
        trailing_payload = _parse_trailing_json_payload(content)
        if trailing_payload is not None:
            prefix_content, payload = trailing_payload
            parsed_calls = _normalise_tool_call_payload(payload, prefix="json") if _payload_has_tool_call_shape(payload) else []
            parsed_calls = _filter_tool_calls_by_name(parsed_calls, allowed_tool_names)
            if parsed_calls:
                tool_calls.extend(parsed_calls)
                stripped_content = prefix_content

    if not tool_calls:
        return content, []
    return stripped_content.strip(), tool_calls


def _extract_tool_code_calls(content: str) -> tuple[str, list[dict[str, Any]]]:
    tool_calls: list[dict[str, Any]] = []

    def _consume(match: re.Match[str]) -> str:
        parsed = _parse_tool_code_calls(match.group("body"))
        tool_calls.extend(parsed)
        return "" if parsed else match.group(0)

    stripped_content = _TOOL_CODE_RE.sub(_consume, content)
    if not tool_calls:
        parsed = _parse_tool_code_calls(content)
        if parsed:
            return "", parsed
        return content, []
    return stripped_content.strip(), tool_calls


def _normalize_ai_message_tool_calls(message: AIMessage, *, allowed_tool_names: set[str] | None = None) -> AIMessage:
    if message.tool_calls:
        return message
    raw_tool_calls = _extract_additional_kwargs_tool_calls(message)
    if raw_tool_calls:
        return message.model_copy(update={"tool_calls": raw_tool_calls})

    if isinstance(message.content, list):
        kept_content, block_tool_calls = _extract_content_block_tool_calls(message.content)
        if block_tool_calls:
            return message.model_copy(update={"content": kept_content, "tool_calls": block_tool_calls})
        return message

    if not isinstance(message.content, str):
        return message
    normalized_content, tool_calls = _extract_llamacpp_tool_calls(message.content)
    if not tool_calls:
        normalized_content, tool_calls = _extract_xmlish_tool_calls(message.content)
    if not tool_calls:
        normalized_content, tool_calls = _extract_orphan_xmlish_function_calls(message.content)
    if not tool_calls:
        normalized_content, tool_calls = _extract_bare_xml_tool_calls(message.content, allowed_tool_names=allowed_tool_names)
    if not tool_calls:
        normalized_content, tool_calls = _extract_jsonish_tool_calls(message.content, allowed_tool_names=allowed_tool_names)
    if not tool_calls:
        normalized_content, tool_calls = _extract_tool_code_calls(message.content)
    if not tool_calls:
        return message
    return message.model_copy(
        update={
            "content": normalized_content,
            "tool_calls": tool_calls,
        }
    )


def _normalize_chat_result_tool_calls(result: ChatResult, *, allowed_tool_names: set[str] | None = None) -> ChatResult:
    generations = []
    changed = False
    for generation in result.generations:
        message = getattr(generation, "message", None)
        if not isinstance(message, AIMessage):
            generations.append(generation)
            continue
        normalized_message = _normalize_ai_message_tool_calls(message, allowed_tool_names=allowed_tool_names)
        if normalized_message is not message:
            changed = True
            generations.append(generation.model_copy(update={"message": normalized_message}))
            continue
        generations.append(generation)
    if not changed:
        return result
    return result.model_copy(update={"generations": generations})


def _ai_message_from_chunk(chunk: AIMessageChunk) -> AIMessage:
    return AIMessage(
        content=chunk.content,
        additional_kwargs=dict(getattr(chunk, "additional_kwargs", {}) or {}),
        response_metadata=dict(getattr(chunk, "response_metadata", {}) or {}),
        id=getattr(chunk, "id", None),
        tool_calls=list(getattr(chunk, "tool_calls", []) or []),
        invalid_tool_calls=list(getattr(chunk, "invalid_tool_calls", []) or []),
        usage_metadata=getattr(chunk, "usage_metadata", None),
    )


def _chunk_from_ai_message(message: AIMessage) -> AIMessageChunk:
    return AIMessageChunk(
        content=message.content,
        additional_kwargs=dict(getattr(message, "additional_kwargs", {}) or {}),
        response_metadata=dict(getattr(message, "response_metadata", {}) or {}),
        id=getattr(message, "id", None),
        tool_calls=list(getattr(message, "tool_calls", []) or []),
        invalid_tool_calls=list(getattr(message, "invalid_tool_calls", []) or []),
        usage_metadata=getattr(message, "usage_metadata", None),
        chunk_position="last",
    )


def _normalize_chat_generation_chunks(chunks: list[ChatGenerationChunk], *, allowed_tool_names: set[str] | None = None) -> list[ChatGenerationChunk]:
    if not chunks:
        return chunks

    aggregated = chunks[0]
    for chunk in chunks[1:]:
        aggregated += chunk

    message = getattr(aggregated, "message", None)
    if not isinstance(message, AIMessageChunk):
        return chunks

    normalized_message = _normalize_ai_message_tool_calls(_ai_message_from_chunk(message), allowed_tool_names=allowed_tool_names)
    if not normalized_message.tool_calls:
        return chunks

    return [
        ChatGenerationChunk(
            message=_chunk_from_ai_message(normalized_message),
            generation_info=getattr(aggregated, "generation_info", None),
        )
    ]


_TOOL_TEXT_STARTS = (
    "<tool_call",
    "<tool_calls",
    "<function=",
    "<|tool_code|>",
    "<|tool_call:",
    "<|call:",
    "```json",
    "```tool_code",
    "```tool_call",
    "```tool_calls",
)


def _chunk_text(chunk: ChatGenerationChunk) -> str:
    message = getattr(chunk, "message", None)
    if not isinstance(message, AIMessageChunk):
        return ""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
        return "".join(text_parts)
    return ""


def _has_structured_tool_signal(chunk: ChatGenerationChunk) -> bool:
    message = getattr(chunk, "message", None)
    if not isinstance(message, AIMessageChunk):
        return False
    if getattr(message, "tool_calls", None) or getattr(message, "tool_call_chunks", None):
        return True
    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    return bool(additional_kwargs.get("tool_calls") or additional_kwargs.get("function_call"))


def _looks_like_buffered_tool_text(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if stripped[0] in {"{", "["}:
        return True
    if any(lowered.startswith(marker) for marker in _TOOL_TEXT_STARTS):
        return True
    return any(marker.startswith(lowered) for marker in _TOOL_TEXT_STARTS if len(lowered) < len(marker))


def _normalize_streaming_chat_generation_chunks(
    chunks: Iterable[ChatGenerationChunk],
    *,
    allowed_tool_names: set[str] | None = None,
) -> Iterable[ChatGenerationChunk]:
    buffered: list[ChatGenerationChunk] = []

    for chunk in chunks:
        if buffered:
            buffered.append(chunk)
            continue

        if _has_structured_tool_signal(chunk):
            yield chunk
            continue

        text = _chunk_text(chunk)
        if text and _looks_like_buffered_tool_text(text):
            buffered.append(chunk)
            continue

        yield chunk

    if buffered:
        yield from _normalize_chat_generation_chunks(buffered, allowed_tool_names=allowed_tool_names)


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
        return _normalize_chat_result_tool_calls(result, allowed_tool_names=_invocation_tool_names(self.bound_tools_list, merged))

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
        return _normalize_chat_result_tool_calls(result, allowed_tool_names=_invocation_tool_names(self.bound_tools_list, merged))

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ):
        normalized_messages = self.translator.normalize_messages(messages, self.semantic_profile)
        merged = {**kwargs, **self.bound_invocation_kwargs()}
        yield from _normalize_streaming_chat_generation_chunks(
            self.wrapped_model._stream(normalized_messages, stop=stop, run_manager=run_manager, **merged),
            allowed_tool_names=_invocation_tool_names(self.bound_tools_list, merged),
        )

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ):
        normalized_messages = self.translator.normalize_messages(messages, self.semantic_profile)
        merged = {**kwargs, **self.bound_invocation_kwargs()}
        buffered: list[ChatGenerationChunk] = []
        async for chunk in self.wrapped_model._astream(normalized_messages, stop=stop, run_manager=run_manager, **merged):
            if buffered:
                buffered.append(chunk)
                continue
            if _has_structured_tool_signal(chunk):
                yield chunk
                continue
            text = _chunk_text(chunk)
            if text and _looks_like_buffered_tool_text(text):
                buffered.append(chunk)
                continue
            yield chunk
        if buffered:
            for chunk in _normalize_chat_generation_chunks(buffered, allowed_tool_names=_invocation_tool_names(self.bound_tools_list, merged)):
                yield chunk
