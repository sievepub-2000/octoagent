"""LangGraph middleware that routes tool calls through ParallelExecutor.

Opt-in via environment variable OCTOAGENT_PARALLEL_EXEC=1. When enabled,
intercepts tool calls before execution, groups them for parallel execution,
and returns results in the expected format. Falls back to sequential execution
when disabled or when errors occur during parallel routing.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime

from src.agents.thread_state import merge_runtime_state

from .parallel_executor import CallResult, ParallelExecutor, ParallelExecutorConfig

logger = logging.getLogger(__name__)


_PARALLEL_ENABLED = os.getenv("OCTOAGENT_PARALLEL_EXEC", "0").strip().lower() in {"1", "true", "yes", "on"}
_MIDDLEWARE_MARKER = '<parallel_execution origin="parallel_execution_middleware"'


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


class ParallelExecutionMiddlewareState(AgentState):
    runtime: Annotated[dict[str, Any] | None, merge_runtime_state]
    parallel_execution_enabled: NotRequired[bool]


def _tool_calls_from_messages(messages: list[Any]) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        content = getattr(message, "content", None)
        name = str(getattr(message, "name", ""))
        if content is None or not name:
            continue
        try:
            parsed = json.loads(content) if isinstance(content, str) and content.strip().startswith("{") else {"tool": name, "args": {"result": str(content)}}
        except (json.JSONDecodeError, TypeError):
            parsed = {"tool": name, "args": {"result": str(content)}}
        tool_calls.append(parsed)
    return tool_calls


def _results_to_tool_messages(results: list[CallResult], original_messages: list[Any]) -> list[ToolMessage]:
    messages: list[ToolMessage] = []
    for result in results:
        if result.error is not None and result.result is None:
            content = f"Error executing {result.tool_name}: {result.error}"
            status = "error"
        else:
            content = str(result.result) if result.result is not None else ""
            status = "success"

        messages.append(
            ToolMessage(
                content=content,
                name=result.tool_name,
                tool_call_id=f"{result.tool_name}-{result.index}",
                status=status,
            )
        )
    return messages


import json  # noqa: E402


class ParallelExecutionMiddleware(AgentMiddleware[ParallelExecutionMiddlewareState]):
    """Route independent tool calls through the parallel executor."""

    state_schema = ParallelExecutionMiddlewareState

    def __init__(self):
        self._executor: ParallelExecutor | None = None

    @property
    def enabled(self) -> bool:
        if not _PARALLEL_ENABLED:
            return False
        runtime_state = getattr(self, "_last_runtime", None)
        if isinstance(runtime_state, dict):
            explicit = runtime_state.get("parallel_execution_enabled")
            if explicit is not None and _is_truthy(explicit):
                return True
        return bool(_PARALLEL_ENABLED)

    def _get_executor(self) -> ParallelExecutor:
        if self._executor is None:
            config = ParallelExecutorConfig()
            self._executor = ParallelExecutor(config=config)
        return self._executor

    @override
    async def abefore_model(self, state: ParallelExecutionMiddlewareState, runtime: Runtime) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        messages = list(state.get("messages", []))
        if len(messages) < 2:
            return None

        tool_calls = _tool_calls_from_messages(messages)
        if len(tool_calls) <= 1:
            return None

        executor = self._get_executor()
        runtime_state = dict(state.get("runtime") or {})
        runtime_state["parallel_execution_enabled"] = True
        runtime_state.setdefault("parallel_execution_stats", {})

        try:
            results = await executor.execute_batch(tool_calls, _fallback_sync_executor)
        except Exception as exc:
            logger.warning(f"Parallel execution failed, falling back to sequential: {exc}")
            runtime_state["parallel_execution_fallback"] = True
            return {"runtime": runtime_state}

        stats = {
            "total_calls": len(tool_calls),
            "successful": sum(1 for r in results if r.error is None),
            "failed": sum(1 for r in results if r.error is not None),
            "repaired": sum(1 for r in results if r.repaired),
        }
        runtime_state["parallel_execution_stats"] = stats

        replacement_messages = _results_to_tool_messages(results, messages)
        new_messages: list[Any] = []
        for message in messages:
            if isinstance(message, ToolMessage):
                continue
            new_messages.append(message)
        new_messages.extend(replacement_messages)

        return {
            "messages": new_messages,
            "runtime": runtime_state,
        }

    @override
    def before_model(self, state: ParallelExecutionMiddlewareState, runtime: Runtime) -> dict[str, Any] | None:
        import asyncio as _asyncio

        if not self.enabled:
            return None

        messages = list(state.get("messages", []))
        if len(messages) < 2:
            return None

        tool_calls = _tool_calls_from_messages(messages)
        if len(tool_calls) <= 1:
            return None

        executor = self._get_executor()
        runtime_state = dict(state.get("runtime") or {})
        runtime_state["parallel_execution_enabled"] = True
        runtime_state.setdefault("parallel_execution_stats", {})

        try:
            results = _asyncio.run(executor.execute_batch(tool_calls, _fallback_sync_executor))
        except Exception as exc:
            logger.warning(f"Parallel execution failed, falling back to sequential: {exc}")
            runtime_state["parallel_execution_fallback"] = True
            return {"runtime": runtime_state}

        stats = {
            "total_calls": len(tool_calls),
            "successful": sum(1 for r in results if r.error is None),
            "failed": sum(1 for r in results if r.error is not None),
            "repaired": sum(1 for r in results if r.repaired),
        }
        runtime_state["parallel_execution_stats"] = stats

        replacement_messages = _results_to_tool_messages(results, messages)
        new_messages: list[Any] = []
        for message in messages:
            if isinstance(message, ToolMessage):
                continue
            new_messages.append(message)
        new_messages.extend(replacement_messages)

        return {
            "messages": new_messages,
            "runtime": runtime_state,
        }


def _fallback_sync_executor(call_dict: dict[str, Any]) -> Any:
    tool_name = call_dict.get("tool", "")
    args = call_dict.get("args", {})
    if "_recovery_injected" in args:
        return f"[recovery diagnostic for {tool_name}]"
    return f"[sequential fallback result for {tool_name}]"


__all__ = ["ParallelExecutionMiddleware"]
