"""Middleware for skill evolution — records execution traces and triggers analysis.

Integrates the claw-code SkillEvolution engine into the agent middleware stack.
After each agent execution, builds an ExecutionTrace from the conversation and
feeds it into the SkillAnalyzer → SkillEvolver pipeline.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

try:
    from langgraph.config import get_config as _lg_get_config  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - older langgraph without get_config
    _lg_get_config = None  # type: ignore[assignment]

from src.agents.core.run_record_store import append_run_record
from src.agents.core.run_records import build_execution_run_record
from src.agents.core.termination import classify_run_outcome, is_continuation_announcement
from src.storage.skill_evolution.analyzer import AnalysisSuggestion, ExecutionTrace, SkillAnalyzer
from src.storage.skill_evolution.evolver import SkillEvolver
from src.storage.skill_evolution.planning import (
    build_skill_evolution_planning_hints,
    format_skill_evolution_planning_hints,
)
from src.storage.skill_evolution.registry import SkillEvolutionRegistry
from src.storage.skill_evolution.trust_score import record_invocation
from src.storage.skill_evolution.types import EvolutionConfig

logger = logging.getLogger(__name__)


def _message_content_text(content: Any) -> str:
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def _looks_like_failed_tool_message(msg: Any, content_str: str) -> bool:
    status = getattr(msg, "status", None)
    if status == "error":
        return True
    lowered = content_str.strip().lower()
    return lowered.startswith(
        (
            "error:",
            "failed:",
            "tool error:",
            "tool failed:",
            "exception:",
            "traceback (most recent call last):",
        )
    )


def _looks_like_unfinished_action_announcement(content_str: str) -> bool:
    """Thin wrapper around the central termination detector.

    Kept as a module-local name so older call sites (and tests) continue to
    work, but the vocabulary lives in :mod:`src.agents.core.termination`.
    """
    return is_continuation_announcement(content_str)


def _looks_like_runtime_failure_message(content_str: str) -> bool:
    text = content_str.strip()
    if not text:
        return False
    return '我在执行这轮任务时遇到了运行时错误' in text or '错误类型：NormalizedModelError' in text or '错误类型: NormalizedModelError' in text or 'Cannot have 2 or more assistant messages at the end of the list' in text


def _looks_like_recovery_stop_message(content_str: str) -> bool:
    text = content_str.strip()
    if not text:
        return False
    lowered = text.lower()
    legacy_hard_stop = "".join(chr(code) for code in (0x5de5, 0x5177, 0x8c03, 0x7528, 0x8fde, 0x7eed, 0x5931, 0x8d25))
    legacy_policy_stop = "".join(chr(code) for code in (0x5df2, 0x6309, 0x6062, 0x590d, 0x7b56, 0x7565, 0x505c, 0x6b62))
    return (
        (legacy_hard_stop in text and legacy_policy_stop in text)
        or "tool recovery policy stopped" in lowered
        or "recovery policy stopped before completing" in lowered
    )

def _is_substantive_final_response(content_str: str) -> bool:
    text = content_str.strip()
    if not text:
        return False
    if _looks_like_unfinished_action_announcement(text):
        return False
    if _looks_like_runtime_failure_message(text):
        return False
    if _looks_like_recovery_stop_message(text):
        return False
    return len(text) >= 24


def _extract_execution_trace(messages: list[Any]) -> ExecutionTrace:
    trace = ExecutionTrace()
    skills_used: set[str] = set()
    skills_failed: set[str] = set()
    tools_used: set[str] = set()
    tools_failed: set[str] = set()
    total_tokens = 0
    last_error = ''
    last_error_index = -1
    last_final_ai_text = ''
    last_final_ai_index = -1

    for index, msg in enumerate(messages):
        msg_type = getattr(msg, 'type', '')
        content = getattr(msg, 'content', '')
        content_str = _message_content_text(content)

        if msg_type == 'human' and not trace.task_description:
            trace.task_description = content_str[:300]

        tool_calls = getattr(msg, 'tool_calls', None) or []
        for tc in tool_calls:
            name = tc.get('name', '') if isinstance(tc, dict) else getattr(tc, 'name', '')
            if name:
                tools_used.add(name)
                if name.startswith('skill_') or name.endswith('_skill'):
                    skills_used.add(name)

        if msg_type == 'tool':
            tool_name = getattr(msg, 'name', '')
            if tool_name:
                tools_used.add(tool_name)
            if _looks_like_failed_tool_message(msg, content_str):
                tools_failed.add(tool_name)
                if tool_name.startswith('skill_') or tool_name.endswith('_skill'):
                    skills_failed.add(tool_name)
                last_error = content_str[:200]
                last_error_index = index

        if msg_type == 'ai' and not tool_calls:
            stripped = content_str.strip()
            if stripped:
                last_final_ai_text = stripped
                last_final_ai_index = index
            if _looks_like_unfinished_action_announcement(content_str):
                last_error = 'Assistant ended with an unfinished action announcement.'
                last_error_index = index
            elif _looks_like_runtime_failure_message(content_str):
                last_error = 'Assistant ended with a runtime model error.'
                last_error_index = index
            elif _looks_like_recovery_stop_message(content_str):
                last_error = 'Tool recovery policy stopped before completing the user task.'
                last_error_index = index

        metadata = getattr(msg, 'response_metadata', {}) or {}
        usage = metadata.get('usage', {}) or metadata.get('token_usage', {})
        if usage:
            total_tokens += usage.get('total_tokens', 0)

    recovered_after_error = last_final_ai_index > last_error_index and _is_substantive_final_response(last_final_ai_text)
    if recovered_after_error:
        last_error = ''

    trace.skills_used = list(skills_used)
    trace.skills_failed = list(skills_failed)
    trace.tools_used = list(tools_used)
    trace.tools_failed = list(tools_failed)
    trace.token_usage = total_tokens
    trace.error_message = last_error
    trace.success = not last_error and (not tools_failed or recovered_after_error)

    return trace

class SkillEvolutionMiddleware(AgentMiddleware):
    """Records execution traces and triggers skill evolution after agent runs.

    Uses the ``after_agent`` hook so evolution analysis only fires after a
    complete agent execution.  Evolution mutations are fire-and-forget:
    failures are logged but never block the response.
    """

    def __init__(self, data_dir: Path, skills_root: Path) -> None:
        self._registry = SkillEvolutionRegistry(data_dir)
        self._config = EvolutionConfig()  # Default config; admin can tune via API
        self._analyzer = SkillAnalyzer()
        self._evolver = SkillEvolver(self._registry, skills_root, self._config)
        self._start_time: float = 0.0

    @override
    def before_agent(self, state: AgentState, runtime: Runtime) -> dict | None:
        """Record start time for latency measurement."""
        if (runtime.context or {}).get("mode") == "flash":
            self._start_time = time.monotonic()
            return None
        self._start_time = time.monotonic()
        hints = build_skill_evolution_planning_hints(
            self._registry,
            task_description=_extract_latest_human_text(state.get("messages", [])),
        )
        rendered = format_skill_evolution_planning_hints(hints)
        if not rendered:
            return None
        messages = list(state.get("messages") or [])
        if not messages:
            return None
        messages.insert(-1, SystemMessage(content=rendered))
        runtime_state = dict(state.get("runtime") or {})
        runtime_state["skill_evolution_hints"] = hints
        return {"messages": messages, "runtime": runtime_state}

    @override
    def after_agent(self, state: AgentState, runtime: Runtime) -> dict | None:
        """Analyze execution and trigger evolution if needed."""
        try:
            runtime_context = runtime.context or {}
            # Fall back to the LangGraph RunnableConfig when the run-scoped
            # context omits identifiers. ``runtime.context`` is set by the
            # graph entry point; ``configurable`` is always populated by the
            # LangGraph runtime itself, so it makes run_records correlatable.
            cfg_configurable: dict[str, Any] = {}
            if _lg_get_config is not None:
                try:
                    cfg = _lg_get_config()
                    cfg_configurable = dict((cfg or {}).get("configurable") or {})
                except Exception:  # pragma: no cover - outside graph execution
                    cfg_configurable = {}
            thread_id_value = (
                str(runtime_context.get("thread_id") or "")
                or str(cfg_configurable.get("thread_id") or "")
            ) or None
            agent_name_value = (
                str(runtime_context.get("agent_name") or "")
                or str(cfg_configurable.get("agent_name") or "")
            ) or None
            run_id_value = (
                str(cfg_configurable.get("run_id") or "")
                or str(runtime_context.get("run_id") or "")
            ) or None
            messages = state.get("messages", [])
            if not messages:
                return None

            elapsed_ms = (time.monotonic() - self._start_time) * 1000

            # Build trace
            trace = _extract_execution_trace(messages)

            # Record metrics for every skill used
            for skill_name in trace.skills_used:
                skill_success = skill_name not in trace.skills_failed
                self._registry.record_execution(
                    skill_name,
                    success=skill_success,
                    latency_ms=elapsed_ms,
                )
                record_invocation(
                    skill_name,
                    success=skill_success,
                    latency_ms=elapsed_ms,
                    extra={
                        "thread_id": thread_id_value or "",
                        "agent_name": agent_name_value or "",
                    },
                )

            runtime_state = dict(state.get("runtime") or {})
            outcome = classify_run_outcome(messages)
            structurally_complete = outcome.status == "completed"
            if trace.success and structurally_complete:
                runtime_state["recoverable_failure"] = None
                runtime_state["incomplete_state"] = None
            else:
                reason = trace.error_message or outcome.reason or "Agent run ended before completing the user task."
                recoverable_failure = {
                    "status": "recoverable",
                    "reason": reason,
                    "next_action": "continue from persisted task state and avoid repeating failed tool paths",
                }
                runtime_state["recoverable_failure"] = recoverable_failure
                runtime_state["incomplete_state"] = recoverable_failure
                runtime_state["recommended_memory_action"] = "continue"
            record_reason = None if trace.success and structurally_complete else trace.error_message or outcome.reason
            run_record = build_execution_run_record(
                {
                    **state,
                    "runtime": runtime_state,
                },
                final_status="completed" if trace.success and structurally_complete else None,
                evaluation_reason=record_reason,
            )
            runtime_state["last_run_record"] = append_run_record(
                run_record,
                thread_id=thread_id_value,
                agent_name=agent_name_value,
                run_id=run_id_value,
            )

            if runtime_context.get("mode") == "flash":
                runtime_state["skill_evolution_suggestions"] = []
                return {"runtime": runtime_state}

            # Analyze and evolve
            suggestions: list[AnalysisSuggestion] = self._analyzer.analyze(trace)
            runtime_state["skill_evolution_suggestions"] = [
                {
                    "skill_name": suggestion.skill_name,
                    "mode": suggestion.mode.value,
                    "reason": suggestion.reason,
                    "confidence": suggestion.confidence,
                }
                for suggestion in suggestions
            ]
            if suggestions:
                logger.info(
                    "Skill evolution analysis produced %d suggestion(s): %s",
                    len(suggestions),
                    [(s.skill_name, s.mode.value) for s in suggestions],
                )
                for suggestion in suggestions:
                    try:
                        self._evolver.evolve(suggestion)
                    except Exception:
                        logger.warning(
                            "Failed to evolve skill %s (%s)",
                            suggestion.skill_name,
                            suggestion.mode.value,
                            exc_info=True,
                        )
            return {"runtime": runtime_state}

        except Exception:
            logger.warning("SkillEvolutionMiddleware.after_agent failed", exc_info=True)

        return None  # Never block the main response


def _extract_latest_human_text(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "human":
            content = getattr(msg, "content", "")
            if isinstance(content, list):
                return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            return str(content or "")
    return ""
