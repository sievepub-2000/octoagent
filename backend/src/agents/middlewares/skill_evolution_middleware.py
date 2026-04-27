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
from langgraph.runtime import Runtime

from src.skill_evolution.analyzer import AnalysisSuggestion, ExecutionTrace, SkillAnalyzer
from src.skill_evolution.evolver import SkillEvolver
from src.skill_evolution.registry import SkillEvolutionRegistry
from src.skill_evolution.types import EvolutionConfig

logger = logging.getLogger(__name__)


def _extract_execution_trace(messages: list[Any]) -> ExecutionTrace:
    """Build an ExecutionTrace from LangChain message objects."""
    trace = ExecutionTrace()
    skills_used: set[str] = set()
    skills_failed: set[str] = set()
    tools_used: set[str] = set()
    tools_failed: set[str] = set()
    total_tokens = 0
    last_error = ""

    for msg in messages:
        msg_type = getattr(msg, "type", "")
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        content_str = str(content)

        # Extract task description from first human message
        if msg_type == "human" and not trace.task_description:
            trace.task_description = content_str[:300]

        # Track tool calls from AI messages
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in tool_calls:
            name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            if name:
                tools_used.add(name)
                # Skills are tools with special naming convention
                if name.startswith("skill_") or name.endswith("_skill"):
                    skills_used.add(name)

        # Track tool failures
        if msg_type == "tool":
            tool_name = getattr(msg, "name", "")
            if tool_name:
                tools_used.add(tool_name)
            # Check for error indicators
            if "error" in content_str.lower() or "failed" in content_str.lower():
                tools_failed.add(tool_name)
                if tool_name.startswith("skill_") or tool_name.endswith("_skill"):
                    skills_failed.add(tool_name)
                last_error = content_str[:200]

        # Estimate token usage from response metadata
        metadata = getattr(msg, "response_metadata", {}) or {}
        usage = metadata.get("usage", {}) or metadata.get("token_usage", {})
        if usage:
            total_tokens += usage.get("total_tokens", 0)

    trace.skills_used = list(skills_used)
    trace.skills_failed = list(skills_failed)
    trace.tools_used = list(tools_used)
    trace.tools_failed = list(tools_failed)
    trace.token_usage = total_tokens
    trace.error_message = last_error
    trace.success = len(tools_failed) == 0

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
        self._start_time = time.monotonic()
        return None

    @override
    def after_agent(self, state: AgentState, runtime: Runtime) -> dict | None:
        """Analyze execution and trigger evolution if needed."""
        try:
            messages = state.get("messages", [])
            if not messages:
                return None

            elapsed_ms = (time.monotonic() - self._start_time) * 1000

            # Build trace
            trace = _extract_execution_trace(messages)

            # Record metrics for every skill used
            for skill_name in trace.skills_used:
                self._registry.record_execution(
                    skill_name,
                    success=skill_name not in trace.skills_failed,
                    latency_ms=elapsed_ms,
                )

            # Analyze and evolve
            suggestions: list[AnalysisSuggestion] = self._analyzer.analyze(trace)
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

        except Exception:
            logger.warning("SkillEvolutionMiddleware.after_agent failed", exc_info=True)

        return None  # Never mutate state
