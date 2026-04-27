import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain.chat_models import BaseChatModel
from langchain_core.language_models.chat_models import BaseChatModel as CoreBaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from pydantic import ConfigDict, Field

from src.config import get_app_config, get_tracing_config, is_tracing_enabled
from src.config.embedded_model_config import get_embedded_model_config
from src.models.provider_adapter import (
    ProviderAdapterChatModel,
    resolve_provider_adapter_profile,
)
from src.models.runtime_telemetry import (
    record_fallback_switch,
    record_final_error,
    set_active_model,
)
from src.models.semantics import ModelSemanticTranslator
from src.reflection import resolve_class

logger = logging.getLogger(__name__)
EMBEDDED_BACKUP_MODEL_NAME = "__embedded_bootstrap__"
_semantic_translator = ModelSemanticTranslator()


def _get_model_priority(model_config) -> int:
    priority = getattr(model_config, "priority", 0)
    return priority if isinstance(priority, int) else 0


def _get_model_profile_tags(model_config) -> set[str]:
    tags = getattr(model_config, "profile_tags", None) or []
    if not isinstance(tags, list):
        return set()
    return {str(tag).strip().lower() for tag in tags if str(tag).strip()}


def _supports_required_capabilities(
    model_config,
    *,
    thinking_enabled: bool,
    requires_vision: bool,
    min_context_tokens: int | None,
) -> bool:
    del thinking_enabled
    if requires_vision and not model_config.supports_vision:
        return False
    if min_context_tokens is not None and model_config.max_context_tokens is not None:
        if model_config.max_context_tokens < min_context_tokens:
            return False
    return True


def _score_model_config(
    model_config,
    *,
    selection_profile: str,
    thinking_enabled: bool,
    requires_vision: bool,
    min_context_tokens: int | None,
) -> int | None:
    if not _supports_required_capabilities(
        model_config,
        thinking_enabled=thinking_enabled,
        requires_vision=requires_vision,
        min_context_tokens=min_context_tokens,
    ):
        return None

    score = _get_model_priority(model_config)
    tags = _get_model_profile_tags(model_config)
    profile = selection_profile.strip().lower()

    if profile and profile in tags:
        score += 100
    if thinking_enabled and model_config.supports_thinking:
        score += 20
    if requires_vision and model_config.supports_vision:
        score += 20
    if min_context_tokens is not None and model_config.max_context_tokens is not None:
        score += min(model_config.max_context_tokens // 1000, 50)
    return score


def _select_default_model_name(
    *,
    thinking_enabled: bool,
    selection_profile: str,
    requires_vision: bool,
    min_context_tokens: int | None,
) -> str | None:
    config = get_app_config()
    best_name: str | None = None
    best_score: int | None = None
    for model in config.models:
        score = _score_model_config(
            model,
            selection_profile=selection_profile,
            thinking_enabled=thinking_enabled,
            requires_vision=requires_vision,
            min_context_tokens=min_context_tokens,
        )
        if score is None:
            continue
        if thinking_enabled and not model.supports_thinking:
            continue
        if best_score is None or score > best_score:
            best_score = score
            best_name = model.name
    return best_name


def _should_fallback_model(exc: Exception) -> bool:
    message = str(exc).lower()
    fallback_markers = [
        "context length",
        "maximum context",
        "maximum token",
        "too many tokens",
        "token limit",
        "rate limit",
        "rate-limited",
        "temporarily rate-limited",
        "429",
        "503",
        "timeout",
        "timed out",
        "connection",
        "temporarily unavailable",
        "service unavailable",
        "overloaded",
        "network",
        "refused",
    ]
    return any(marker in message for marker in fallback_markers)


# ---------------------------------------------------------------------------
# Context window safety trimming
# ---------------------------------------------------------------------------

_MAX_ESTIMATED_TOKENS = 200_000  # Hard safety ceiling
_KEEP_RECENT_MESSAGES = 20  # Keep system msgs + last N messages

def _estimate_message_tokens(messages: list[BaseMessage]) -> int:
    """Rough token estimate: 1 token ≈ 4 ASCII chars, 1 token ≈ 1.5 CJK chars."""
    total = 0
    for m in messages:
        content = m.content
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
            )
        text = str(content)
        ascii_count = sum(1 for c in text if ord(c) < 128)
        non_ascii = len(text) - ascii_count
        total += max(1, int(ascii_count / 4 + non_ascii / 1.5))
    return total


def _trim_messages_if_needed(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Drop old messages if estimated tokens exceed safety ceiling."""
    est = _estimate_message_tokens(messages)
    if est <= _MAX_ESTIMATED_TOKENS:
        return messages

    # Keep system messages and the most recent _KEEP_RECENT_MESSAGES
    system_msgs = [m for m in messages if getattr(m, "type", "") == "system"]
    non_system = [m for m in messages if getattr(m, "type", "") != "system"]
    recent = non_system[-_KEEP_RECENT_MESSAGES:]

    trimmed = system_msgs + [
        SystemMessage(content=f"[Context trimmed: {len(non_system) - len(recent)} older messages removed to fit context window]")
    ] + recent

    logger.warning(
        "Context safety trim: %d→%d messages, ~%d→~%d est tokens",
        len(messages), len(trimmed), est, _estimate_message_tokens(trimmed),
    )
    return trimmed


class FallbackChatModel(CoreBaseChatModel):
    """A BaseChatModel wrapper with ordered model fallback support."""

    primary_model_name: str
    candidate_model_names: list[str]
    thinking_enabled: bool = False
    model_kwargs: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "fallback-chat-model"

    def _candidate_model(self, name: str) -> BaseChatModel:
        return _create_chat_model(
            name=name,
            thinking_enabled=self.thinking_enabled,
            enable_fallback=False,
            **self.model_kwargs,
        )

    def _record_success(self, candidate: str) -> None:
        set_active_model(candidate)

    def _record_fallback(self, candidate: str, next_candidate: str, exc: Exception) -> None:
        record_fallback_switch(
            from_model=candidate,
            to_model=next_candidate,
            reason=str(exc),
        )

    def _record_failure(self, exc: Exception) -> None:
        record_final_error(str(exc))

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        messages = _trim_messages_if_needed(messages)
        last_exc: Exception | None = None
        for index, candidate in enumerate(self.candidate_model_names):
            try:
                model = self._candidate_model(candidate)
                merged = {**kwargs, **self._tool_kwargs_for(model)}
                result = model._generate(
                    messages,
                    stop=stop,
                    run_manager=run_manager,
                    **merged,
                )
                self._record_success(candidate)
                return result
            except Exception as exc:
                last_exc = exc
                if index == len(self.candidate_model_names) - 1 or not _should_fallback_model(exc):
                    self._record_failure(exc)
                    raise
                self._record_fallback(candidate, self.candidate_model_names[index + 1], exc)
                logger.warning(
                    "Model '%s' failed; falling back to '%s'. Error: %s",
                    candidate,
                    self.candidate_model_names[index + 1],
                    exc,
                )
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No model candidates available")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        messages = _trim_messages_if_needed(messages)
        last_exc: Exception | None = None
        for index, candidate in enumerate(self.candidate_model_names):
            try:
                model = self._candidate_model(candidate)
                merged = {**kwargs, **self._tool_kwargs_for(model)}
                result = await model._agenerate(
                    messages,
                    stop=stop,
                    run_manager=run_manager,
                    **merged,
                )
                self._record_success(candidate)
                return result
            except Exception as exc:
                last_exc = exc
                if index == len(self.candidate_model_names) - 1 or not _should_fallback_model(exc):
                    self._record_failure(exc)
                    raise
                self._record_fallback(candidate, self.candidate_model_names[index + 1], exc)
                logger.warning(
                    "Model '%s' async call failed; falling back to '%s'. Error: %s",
                    candidate,
                    self.candidate_model_names[index + 1],
                    exc,
                )
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No model candidates available")

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        messages = _trim_messages_if_needed(messages)
        last_exc: Exception | None = None
        for index, candidate in enumerate(self.candidate_model_names):
            try:
                model = self._candidate_model(candidate)
                merged = {**kwargs, **self._tool_kwargs_for(model)}
                yield from model._stream(
                    messages,
                    stop=stop,
                    run_manager=run_manager,
                    **merged,
                )
                self._record_success(candidate)
                return
            except Exception as exc:
                last_exc = exc
                if index == len(self.candidate_model_names) - 1 or not _should_fallback_model(exc):
                    self._record_failure(exc)
                    raise
                self._record_fallback(candidate, self.candidate_model_names[index + 1], exc)
                logger.warning(
                    "Model '%s' stream failed; falling back to '%s'. Error: %s",
                    candidate,
                    self.candidate_model_names[index + 1],
                    exc,
                )
        if last_exc is not None:
            raise last_exc

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        messages = _trim_messages_if_needed(messages)
        last_exc: Exception | None = None
        for index, candidate in enumerate(self.candidate_model_names):
            try:
                model = self._candidate_model(candidate)
                merged = {**kwargs, **self._tool_kwargs_for(model)}
                async for chunk in model._astream(
                    messages,
                    stop=stop,
                    run_manager=run_manager,
                    **merged,
                ):
                    yield chunk
                self._record_success(candidate)
                return
            except Exception as exc:
                last_exc = exc
                if index == len(self.candidate_model_names) - 1 or not _should_fallback_model(exc):
                    self._record_failure(exc)
                    raise
                self._record_fallback(candidate, self.candidate_model_names[index + 1], exc)
                logger.warning(
                    "Model '%s' async stream failed; falling back to '%s'. Error: %s",
                    candidate,
                    self.candidate_model_names[index + 1],
                    exc,
                )
        if last_exc is not None:
            raise last_exc

    def bind_tools(
        self,
        tools,
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        # Return a new FallbackChatModel that carries the tool binding so the
        # entire fallback chain is preserved when the agent binds tools.
        bound = self.model_copy()
        bound.bound_tools_list = tools
        bound.bound_tools_kwargs = kwargs
        if tool_choice is not None:
            bound.bound_tools_kwargs["tool_choice"] = tool_choice
        return bound

    # Internal storage for deferred tool binding (set by bind_tools)
    bound_tools_list: list | None = None
    bound_tools_kwargs: dict[str, Any] = Field(default_factory=dict)

    def _tool_kwargs_for(self, model: BaseChatModel) -> dict[str, Any]:
        """Convert bound tools to kwargs passable to model._generate() and friends.

        Uses the model's own ``bind_tools`` to convert tool objects into the
        provider–specific format, then extracts the resulting kwargs dict from
        the ``RunnableBinding`` so they can be merged into ``_generate`` /
        ``_agenerate`` calls directly (calling ``_generate`` on a
        ``RunnableBinding`` does NOT forward bound kwargs).
        """
        if self.bound_tools_list is None:
            return {}
        bound = model.bind_tools(self.bound_tools_list, **self.bound_tools_kwargs)
        if bound is model:
            # Model returned itself (e.g. EmbeddedBootstrapChatModel) — no tool kwargs.
            return {}
        if hasattr(bound, "bound_invocation_kwargs"):
            return dict(bound.bound_invocation_kwargs())
        # RunnableBinding.kwargs contains {"tools": [...], "tool_choice": ...}
        return dict(getattr(bound, "kwargs", {}))


class EmbeddedBootstrapChatModel(CoreBaseChatModel):
    """Emergency fallback model backed by the embedded bootstrap runtime."""

    emergency_reason: str = "primary model unavailable"

    @property
    def _llm_type(self) -> str:
        return "embedded-bootstrap-chat-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        from src.bootstrap.runtime import get_embedded_bootstrap_runtime

        result = get_embedded_bootstrap_runtime().emergency_chat(
            messages,
            emergency_reason=self.emergency_reason,
        )
        set_active_model(EMBEDDED_BACKUP_MODEL_NAME)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=result["message"]))]
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        text = result.generations[0].message.content
        yield ChatGenerationChunk(message=AIMessageChunk(content=str(text)))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        for chunk in self._stream(messages, stop=stop, run_manager=run_manager, **kwargs):
            yield chunk

    def bind_tools(
        self,
        tools,
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        del tools, tool_choice, kwargs
        # The embedded emergency model is text-only. Returning self keeps agent
        # execution alive in fallback mode instead of raising NotImplementedError.
        return self


def is_embedded_backup_model_name(name: str | None) -> bool:
    return name == EMBEDDED_BACKUP_MODEL_NAME


def embedded_backup_enabled() -> bool:
    config = get_embedded_model_config()
    return config.enabled


def _embedded_backup_enabled() -> bool:
    return embedded_backup_enabled()


def _create_chat_model(
    name: str | None = None,
    thinking_enabled: bool = False,
    *,
    enable_fallback: bool = True,
    selection_profile: str = "default",
    requires_vision: bool = False,
    min_context_tokens: int | None = None,
    **kwargs,
) -> BaseChatModel:
    """Create a chat model instance from the config.

    Args:
        name: The name of the model to create. If None, the first model in the config will be used.

    Returns:
        A chat model instance.
    """
    config = get_app_config()
    if name is None:
        selected_name = _select_default_model_name(
            thinking_enabled=thinking_enabled,
            selection_profile=selection_profile,
            requires_vision=requires_vision,
            min_context_tokens=min_context_tokens,
        )
        if selected_name is not None:
            name = selected_name
        elif _embedded_backup_enabled():
            return EmbeddedBootstrapChatModel(
                emergency_reason="no primary model is configured",
            )
        else:
            raise ValueError("No chat models are configured.") from None
    if is_embedded_backup_model_name(name):
        return EmbeddedBootstrapChatModel(
            emergency_reason="the primary model is unavailable or not configured",
        )
    model_config = config.get_model_config(name)
    if model_config is None:
        if _embedded_backup_enabled():
            logger.warning(
                "Model '%s' not found in config; falling back to embedded bootstrap model.",
                name,
            )
            return EmbeddedBootstrapChatModel(
                emergency_reason=f"model '{name}' is not configured",
            )
        raise ValueError(f"Model {name} not found in config") from None
    if not _supports_required_capabilities(
        model_config,
        thinking_enabled=thinking_enabled,
        requires_vision=requires_vision,
        min_context_tokens=min_context_tokens,
    ):
        raise ValueError(
            f"Model {name} does not satisfy the requested runtime capabilities",
        ) from None
    candidate_names = list(dict.fromkeys([name, *model_config.fallback_models]))
    if enable_fallback and _embedded_backup_enabled():
        candidate_names.append(EMBEDDED_BACKUP_MODEL_NAME)
    if enable_fallback and len(candidate_names) > 1:
        return FallbackChatModel(
            primary_model_name=name,
            candidate_model_names=candidate_names,
            thinking_enabled=thinking_enabled,
            model_kwargs=kwargs,
        )
    model_class = resolve_class(model_config.resolved_use(), BaseChatModel)
    model_settings_from_config = model_config.model_dump(
        exclude_none=True,
        exclude={
            "use",
            "name",
            "display_name",
            "description",
            "interface_type",
            "provider_name",
            "supports_thinking",
            "supports_reasoning_effort",
            "when_thinking_enabled",
            "thinking",
            "supports_vision",
            "fallback_models",
            "max_context_tokens",
            "provider_family",
            "semantic_format",
            "priority",
            "profile_tags",
        },
    )
    semantic_profile = _semantic_translator.build_profile(model_config)
    model_settings_from_config, kwargs = _semantic_translator.apply_runtime_semantics(
        model_config=model_config,
        profile=semantic_profile,
        thinking_enabled=thinking_enabled,
        model_settings_from_config=model_settings_from_config,
        runtime_kwargs=kwargs,
    )

    model_instance = model_class(**kwargs, **model_settings_from_config)

    if is_tracing_enabled():
        try:
            from langchain_core.tracers.langchain import LangChainTracer

            tracing_config = get_tracing_config()
            tracer = LangChainTracer(
                project_name=tracing_config.project,
            )
            existing_callbacks = model_instance.callbacks or []
            model_instance.callbacks = [*existing_callbacks, tracer]
            logger.debug(f"LangSmith tracing attached to model '{name}' (project='{tracing_config.project}')")
        except Exception as e:
            logger.warning(f"Failed to attach LangSmith tracing to model '{name}': {e}")
    adapter_profile = resolve_provider_adapter_profile(model_config)
    return ProviderAdapterChatModel(
        model_name=model_config.name,
        provider_name=model_config.provider_name,
        adapter_profile=adapter_profile,
        wrapped_model=model_instance,
        semantic_profile=semantic_profile,
        translator=_semantic_translator,
    )


def create_chat_model(name: str | None = None, thinking_enabled: bool = False, **kwargs) -> BaseChatModel:
    return _create_chat_model(name=name, thinking_enabled=thinking_enabled, enable_fallback=True, **kwargs)
