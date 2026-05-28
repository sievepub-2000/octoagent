import json
import logging
import os
import re
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

from langchain.chat_models import BaseChatModel
from langchain_core.language_models.chat_models import BaseChatModel as CoreBaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from pydantic import ConfigDict, Field

from src.harness.reflection import resolve_class
from src.models.error_contracts import NormalizedModelError
from src.models.openrouter import (
    apply_openrouter_request_options,
    is_openrouter_model_config,
)
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
from src.runtime.config import get_app_config, get_tracing_config, is_tracing_enabled
from src.runtime.config.embedded_model_config import get_embedded_model_config
from src.runtime.context_budget import (
    SYSTEM_SESSION_CONTINUE_PROMPT,
    estimate_message_tokens,
    message_content_text,
    select_system_messages_to_budget,
    trim_message_to_token_budget,
    trim_messages_to_budget,
)

logger = logging.getLogger(__name__)
__all__ = ["SYSTEM_SESSION_CONTINUE_PROMPT"]
_MODEL_COOLDOWNS: dict[str, float] = {}


def _model_cooldown_file() -> Path:
    configured = os.environ.get("OCTOAGENT_MODEL_COOLDOWN_FILE")
    if configured:
        return Path(configured)
    runtime_dir = os.environ.get("OCTOAGENT_RUNTIME_CONFIG_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "model_cooldowns.json"
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "runtime" / "model_cooldowns.json"


_MODEL_COOLDOWN_FILE = _model_cooldown_file()
EMBEDDED_BACKUP_MODEL_NAME = "__embedded_bootstrap__"
_semantic_translator = ModelSemanticTranslator()
_FALLBACKABLE_STATUS_CODES = {400, 404, 408, 429, 500, 502, 503, 504}


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
    if isinstance(exc, NormalizedModelError):
        if exc.code == "authentication_failed" or exc.status_code in {401, 403}:
            return False
        if exc.retryable or exc.status_code in _FALLBACKABLE_STATUS_CODES:
            return True
        if exc.code in {"context_length_exceeded", "model_not_found", "upstream_unavailable"}:
            return True
    message = str(exc).lower()
    fallback_markers = [
        "context length",
        "context size",
        "available context size",
        "exceed_context_size",
        "exceeds the available context",
        "maximum context",
        "maximum token",
        "too many tokens",
        "token limit",
        "rate limit",
        "rate-limited",
        "temporarily rate-limited",
        "429",
        "404",
        "not found",
        "model not found",
        "503",
        "502",
        "504",
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


def _cooldown_seconds_for(exc: Exception) -> float:
    if isinstance(exc, NormalizedModelError):
        if exc.status_code == 404 or exc.code == "model_not_found":
            return 6 * 60 * 60
        if exc.status_code == 429 or exc.code == "rate_limit_exceeded":
            return 60.0
        if exc.status_code in {502, 503, 504} or exc.code == "upstream_unavailable":
            return 30.0
    message = str(exc).lower()
    if "quota" in message and ("limit: 0" in message or "free_tier" in message):
        return 6 * 60 * 60
    retry_match = re.search(r"retry(?:delay| in)?[^0-9]{0,20}(\d+)", message)
    if retry_match:
        return max(10.0, min(float(retry_match.group(1)), 180.0))
    if "429" in message or "quota" in message or "rate limit" in message or "rate-limited" in message:
        return 60.0
    if "503" in message or "temporarily unavailable" in message or "overloaded" in message:
        return 30.0
    if "timeout" in message or "timed out" in message or "connection" in message:
        return 15.0
    return 0.0


def _is_paid_model_config(model_config) -> bool:
    pricing_tier = str(getattr(model_config, "pricing_tier", "") or "").strip().lower()
    if pricing_tier == "paid":
        return True
    name = str(getattr(model_config, "name", "") or "").strip().lower()
    display_name = str(getattr(model_config, "display_name", "") or "").strip().lower()
    return name.endswith("-paid") or "(paid)" in display_name


def _model_settings_exclude_fields() -> set[str]:
    return {
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
        "pricing_tier",
        "source",
        "supports_prompt_cache",
        "auto_injected_free_pool",
        # Model-auth metadata is for OctoAgent routing/UI, not provider constructors.
        "auth_mode",
        "conversation_url",
    }


def _implicit_fallback_model_names(
    primary_name: str,
    *,
    thinking_enabled: bool,
    selection_profile: str,
    requires_vision: bool,
    min_context_tokens: int | None,
    max_candidates: int = 3,
) -> list[str]:
    config = get_app_config()
    scored: list[tuple[int, int, str]] = []
    for index, candidate in enumerate(config.models):
        if candidate.name == primary_name or _is_paid_model_config(candidate):
            continue
        if thinking_enabled and not candidate.supports_thinking:
            continue
        score = _score_model_config(
            candidate,
            selection_profile=selection_profile,
            thinking_enabled=thinking_enabled,
            requires_vision=requires_vision,
            min_context_tokens=min_context_tokens,
        )
        if score is None:
            continue
        scored.append((score, -index, candidate.name))
    scored.sort(reverse=True)
    return [name for _, _, name in scored[:max_candidates]]


def resolve_effective_fallback_model_names(
    model_name: str,
    *,
    thinking_enabled: bool = False,
    selection_profile: str = "default",
    requires_vision: bool = False,
    min_context_tokens: int | None = None,
    include_embedded_backup: bool = True,
) -> list[str]:
    """Return explicit and runtime-inferred fallback names for a model."""
    config = get_app_config()
    model_config = config.get_model_config(model_name)
    if model_config is None:
        return [EMBEDDED_BACKUP_MODEL_NAME] if include_embedded_backup and _embedded_backup_enabled() else []
    effective = [
        *model_config.fallback_models,
        *_implicit_fallback_model_names(
            model_name,
            thinking_enabled=thinking_enabled,
            selection_profile=selection_profile,
            requires_vision=requires_vision,
            min_context_tokens=min_context_tokens,
        ),
    ]
    if include_embedded_backup and _embedded_backup_enabled():
        effective.append(EMBEDDED_BACKUP_MODEL_NAME)
    return [name for name in dict.fromkeys(effective) if name != model_name]


def _mark_model_cooldown(model_name: str, exc: Exception) -> None:
    seconds = _cooldown_seconds_for(exc)
    if seconds <= 0:
        return
    until = time.time() + seconds
    previous = _MODEL_COOLDOWNS.get(model_name, 0.0)
    _MODEL_COOLDOWNS[model_name] = max(previous, until)
    _persist_model_cooldowns()
    logger.warning(
        "Model '%s' put on fallback cooldown for %.0fs after transient error.",
        model_name,
        seconds,
    )


def _model_cooldown_remaining(model_name: str) -> float:
    _load_model_cooldowns()
    remaining = _MODEL_COOLDOWNS.get(model_name, 0.0) - time.time()
    if remaining <= 0:
        _MODEL_COOLDOWNS.pop(model_name, None)
        _persist_model_cooldowns()
        return 0.0
    return remaining


def _load_model_cooldowns() -> None:
    if _MODEL_COOLDOWNS or not _MODEL_COOLDOWN_FILE.exists():
        return
    try:
        data = json.loads(_MODEL_COOLDOWN_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            now = time.time()
            for name, until in data.items():
                if isinstance(name, str) and isinstance(until, (int, float)) and until > now:
                    _MODEL_COOLDOWNS[name] = float(until)
    except Exception:
        logger.debug("Could not load model cooldown cache", exc_info=True)


def _persist_model_cooldowns() -> None:
    try:
        now = time.time()
        active = {name: until for name, until in _MODEL_COOLDOWNS.items() if until > now}
        if active:
            _MODEL_COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
            _MODEL_COOLDOWN_FILE.write_text(json.dumps(active), encoding="utf-8")
        elif _MODEL_COOLDOWN_FILE.exists():
            _MODEL_COOLDOWN_FILE.unlink()
    except Exception:
        logger.debug("Could not persist model cooldown cache", exc_info=True)


# ---------------------------------------------------------------------------
# Context window safety trimming
# ---------------------------------------------------------------------------

_MAX_ESTIMATED_TOKENS = 200_000  # Last-resort safety ceiling for unknown model windows
_KEEP_RECENT_MESSAGES = 20  # Keep recent non-system messages that fit the active budget.
_SYSTEM_MESSAGE_BUDGET_RATIO = 0.35
_MODEL_WINDOW_TRIM_RATIO = 0.75
_CONTEXT_RETRY_TRIM_RATIO = 0.5
_CONTEXT_RETRY_MAX_TOKENS = 6_000


def _estimate_message_tokens(messages: list[BaseMessage]) -> int:
    return estimate_message_tokens(messages, overhead=0)


def _message_content_text(message: BaseMessage) -> str:
    return message_content_text(message)


def _trim_message_to_token_budget(message: BaseMessage, max_tokens: int) -> BaseMessage:
    return trim_message_to_token_budget(message, max_tokens)


def _append_message_within_budget(
    selected: list[tuple[int, BaseMessage]],
    *,
    index: int,
    message: BaseMessage,
    budget_tokens: int,
    current_tokens: int,
) -> int:
    message_tokens = _estimate_message_tokens([message])
    if message_tokens <= max(0, budget_tokens - current_tokens):
        selected.append((index, message))
        return current_tokens + message_tokens
    if not selected and budget_tokens > 0:
        selected.append((index, _trim_message_to_token_budget(message, budget_tokens)))
        return _estimate_message_tokens([selected[-1][1]])
    return current_tokens


def _trim_system_messages_to_budget(system_msgs: list[BaseMessage], budget_tokens: int) -> list[BaseMessage]:
    return select_system_messages_to_budget(system_msgs, budget_tokens)


def _context_window_for_model(model_name: str) -> int | None:
    model_config = get_app_config().get_model_config(model_name)
    if model_config is None:
        return None
    max_context_tokens = getattr(model_config, "max_context_tokens", None)
    if isinstance(max_context_tokens, int) and max_context_tokens > 0:
        return max_context_tokens
    return None


def _trim_messages_if_needed(
    messages: list[BaseMessage],
    max_context_tokens: int | None = None,
    *,
    trim_ratio: float = _MODEL_WINDOW_TRIM_RATIO,
    force: bool = False,
) -> list[BaseMessage]:
    """Drop old messages if estimated tokens exceed the active model window."""
    est = _estimate_message_tokens(messages)
    target_tokens = _MAX_ESTIMATED_TOKENS
    if isinstance(max_context_tokens, int) and max_context_tokens > 0:
        target_tokens = min(target_tokens, max(1, int(max_context_tokens * trim_ratio)))
    if est <= target_tokens and not force:
        return messages

    budget_result = trim_messages_to_budget(
        messages,
        target_tokens,
        keep_recent_messages=_KEEP_RECENT_MESSAGES,
        system_budget_ratio=_SYSTEM_MESSAGE_BUDGET_RATIO,
        force=True,
    )
    trimmed = budget_result.messages

    logger.warning(
        "Context safety trim: %d→%d messages, ~%d→~%d est tokens",
        len(messages),
        len(trimmed),
        est,
        budget_result.final_tokens,
    )
    return trimmed


def _is_context_length_error(exc: Exception) -> bool:
    if isinstance(exc, NormalizedModelError):
        return exc.code == "context_length_exceeded"
    return any(
        marker in str(exc).lower()
        for marker in (
            "context length",
            "context window",
            "maximum context",
            "too many tokens",
            "max tokens exceeded",
            "token budget",
            "available context size",
            "exceed_context_size",
        )
    )


def _aggressive_context_retry_messages(messages: list[BaseMessage], max_context_tokens: int | None) -> list[BaseMessage]:
    retry_context_tokens = max_context_tokens
    if isinstance(max_context_tokens, int) and max_context_tokens > 0:
        retry_context_tokens = min(
            max_context_tokens,
            max(1, int(_CONTEXT_RETRY_MAX_TOKENS / _CONTEXT_RETRY_TRIM_RATIO)),
        )
    return _trim_messages_if_needed(
        messages,
        retry_context_tokens,
        trim_ratio=_CONTEXT_RETRY_TRIM_RATIO,
        force=True,
    )


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
        last_exc: Exception | None = None
        for index, candidate in enumerate(self.candidate_model_names):
            remaining = _model_cooldown_remaining(candidate)
            if remaining > 0 and index < len(self.candidate_model_names) - 1:
                logger.info(
                    "Skipping model '%s' during %.0fs fallback cooldown.",
                    candidate,
                    remaining,
                )
                continue
            try:
                model = self._candidate_model(candidate)
                context_window = _context_window_for_model(candidate)
                candidate_messages = _trim_messages_if_needed(messages, context_window)
                merged = {**kwargs, **self._tool_kwargs_for(model)}
                try:
                    result = model._generate(
                        candidate_messages,
                        stop=stop,
                        run_manager=run_manager,
                        **merged,
                    )
                except Exception as inner_exc:
                    if not _is_context_length_error(inner_exc):
                        raise
                    retry_messages = _aggressive_context_retry_messages(messages, context_window)
                    logger.warning(
                        "Model '%s' exceeded context after normal trim; retrying once with aggressive context trim (~%d est tokens).",
                        candidate,
                        _estimate_message_tokens(retry_messages),
                    )
                    result = model._generate(
                        retry_messages,
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
                _mark_model_cooldown(candidate, exc)
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
        last_exc: Exception | None = None
        for index, candidate in enumerate(self.candidate_model_names):
            remaining = _model_cooldown_remaining(candidate)
            if remaining > 0 and index < len(self.candidate_model_names) - 1:
                logger.info(
                    "Skipping model '%s' during %.0fs fallback cooldown.",
                    candidate,
                    remaining,
                )
                continue
            try:
                model = self._candidate_model(candidate)
                context_window = _context_window_for_model(candidate)
                candidate_messages = _trim_messages_if_needed(messages, context_window)
                merged = {**kwargs, **self._tool_kwargs_for(model)}
                try:
                    result = await model._agenerate(
                        candidate_messages,
                        stop=stop,
                        run_manager=run_manager,
                        **merged,
                    )
                except Exception as inner_exc:
                    if not _is_context_length_error(inner_exc):
                        raise
                    retry_messages = _aggressive_context_retry_messages(messages, context_window)
                    logger.warning(
                        "Model '%s' exceeded context after normal async trim; retrying once with aggressive context trim (~%d est tokens).",
                        candidate,
                        _estimate_message_tokens(retry_messages),
                    )
                    result = await model._agenerate(
                        retry_messages,
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
                _mark_model_cooldown(candidate, exc)
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
        last_exc: Exception | None = None
        for index, candidate in enumerate(self.candidate_model_names):
            remaining = _model_cooldown_remaining(candidate)
            if remaining > 0 and index < len(self.candidate_model_names) - 1:
                logger.info(
                    "Skipping model '%s' during %.0fs fallback cooldown.",
                    candidate,
                    remaining,
                )
                continue
            try:
                model = self._candidate_model(candidate)
                context_window = _context_window_for_model(candidate)
                candidate_messages = _trim_messages_if_needed(messages, context_window)
                merged = {**kwargs, **self._tool_kwargs_for(model)}
                try:
                    yield from model._stream(
                        candidate_messages,
                        stop=stop,
                        run_manager=run_manager,
                        **merged,
                    )
                except Exception as inner_exc:
                    if not _is_context_length_error(inner_exc):
                        raise
                    retry_messages = _aggressive_context_retry_messages(messages, context_window)
                    logger.warning(
                        "Model '%s' exceeded context after normal stream trim; retrying once with aggressive context trim (~%d est tokens).",
                        candidate,
                        _estimate_message_tokens(retry_messages),
                    )
                    yield from model._stream(
                        retry_messages,
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
                _mark_model_cooldown(candidate, exc)
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
        last_exc: Exception | None = None
        for index, candidate in enumerate(self.candidate_model_names):
            remaining = _model_cooldown_remaining(candidate)
            if remaining > 0 and index < len(self.candidate_model_names) - 1:
                logger.info(
                    "Skipping model '%s' during %.0fs fallback cooldown.",
                    candidate,
                    remaining,
                )
                continue
            try:
                model = self._candidate_model(candidate)
                context_window = _context_window_for_model(candidate)
                candidate_messages = _trim_messages_if_needed(messages, context_window)
                merged = {**kwargs, **self._tool_kwargs_for(model)}
                try:
                    async for chunk in model._astream(
                        candidate_messages,
                        stop=stop,
                        run_manager=run_manager,
                        **merged,
                    ):
                        yield chunk
                except Exception as inner_exc:
                    if not _is_context_length_error(inner_exc):
                        raise
                    retry_messages = _aggressive_context_retry_messages(messages, context_window)
                    logger.warning(
                        "Model '%s' exceeded context after normal async stream trim; retrying once with aggressive context trim (~%d est tokens).",
                        candidate,
                        _estimate_message_tokens(retry_messages),
                    )
                    async for chunk in model._astream(
                        retry_messages,
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
                _mark_model_cooldown(candidate, exc)
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
        from src.runtime.bootstrap.runtime import get_embedded_bootstrap_runtime

        result = get_embedded_bootstrap_runtime().emergency_chat(
            messages,
            emergency_reason=self.emergency_reason,
        )
        set_active_model(EMBEDDED_BACKUP_MODEL_NAME)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=result["message"]))])

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
    effective_fallbacks = (
        resolve_effective_fallback_model_names(
            name,
            thinking_enabled=thinking_enabled,
            selection_profile=selection_profile,
            requires_vision=requires_vision,
            min_context_tokens=min_context_tokens,
            include_embedded_backup=False,
        )
        if enable_fallback
        else model_config.fallback_models
    )
    candidate_names = list(dict.fromkeys([name, *effective_fallbacks]))
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
        exclude=_model_settings_exclude_fields(),
    )
    semantic_profile = _semantic_translator.build_profile(model_config)
    model_settings_from_config, kwargs = _semantic_translator.apply_runtime_semantics(
        model_config=model_config,
        profile=semantic_profile,
        thinking_enabled=thinking_enabled,
        model_settings_from_config=model_settings_from_config,
        runtime_kwargs=kwargs,
    )
    if is_openrouter_model_config(model_config):
        model_settings_from_config, kwargs = apply_openrouter_request_options(
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
