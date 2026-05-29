"""Middleware for persisting lightweight runtime telemetry into thread state."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse, ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.runtime import Runtime

from src.agents.subagents.executor import get_subagent_runtime_snapshot
from src.agents.subagents.policy import is_host_memory_oom_critical
from src.agents.thread_state import merge_runtime_state
from src.models.factory import (
    EMBEDDED_BACKUP_MODEL_NAME,
    embedded_backup_enabled,
)
from src.models.runtime_telemetry import (
    begin_model_runtime_telemetry,
    clear_model_runtime_telemetry,
    get_model_runtime_telemetry,
)
from src.runtime.config.subagents_config import get_subagents_app_config
from src.utils.datetime import utc_now_iso as _utc_now

logger = logging.getLogger(__name__)


class RuntimeStateMiddlewareState(AgentState):
    """Compatible with the `ThreadState` schema."""

    continuation: NotRequired[dict[str, Any] | None]
    runtime: Annotated[dict[str, Any] | None, merge_runtime_state]
    workflows: NotRequired[list[dict[str, Any]] | None]
    workflow_events: NotRequired[list[dict[str, Any]] | None]




def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _coerce_available_memory(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _compute_memory_guard_state() -> str:
    subagents_config = get_subagents_app_config()
    runtime_snapshot = get_subagent_runtime_snapshot()

    available_memory_gb = _coerce_available_memory(runtime_snapshot.get("available_memory_gb"))
    if not subagents_config.enable_system_memory_guard:
        return "disabled"
    if available_memory_gb is None:
        return "unknown"
    if is_host_memory_oom_critical(available_memory_gb):
        return "tight"
    return "ok"


def _create_runtime_event(kind: str, title: str, detail: str, level: str) -> dict[str, Any]:
    timestamp = _utc_now()
    return {
        "id": f"workflow-event-{timestamp}",
        "kind": kind,
        "title": title,
        "detail": detail,
        "createdAt": timestamp,
        "level": level,
    }


def _trim_error(value: Any, limit: int = 1200) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _runtime_failure_message(exc: BaseException) -> str:
    detail = _trim_error(exc)
    lowered = detail.lower()
    if "exceeds the available context size" in lowered or ("context" in lowered and "tokens" in lowered):
        reason = "模型上下文超过当前服务上限"
        action = "请切换到更大上下文模型，或把任务拆小后重试。我已经把原始错误显示出来，方便继续处理。"
    elif "permission denied" in lowered or isinstance(exc, PermissionError):
        reason = "系统执行或运行时文件权限不足"
        action = "请检查服务用户对运行时目录、工具目录和目标文件的读写/执行权限。"
    elif "timeout" in lowered:
        reason = "模型或工具执行超时"
        action = "请稍后重试，或缩小任务范围后再执行。"
    else:
        reason = exc.__class__.__name__
        action = "我没有假装完成任务；请根据下面的原始错误继续排查。"
    return f"我在执行这轮任务时遇到了运行时错误，当前结果不完整。\n\n错误类型：{reason}\n原始错误：{detail or exc.__class__.__name__}\n\n处理建议：{action}"


class RuntimeStateMiddleware(AgentMiddleware[RuntimeStateMiddlewareState]):
    """Persist a normalized runtime snapshot into thread state."""

    state_schema = RuntimeStateMiddlewareState

    def __init__(self, model_name: str | None, fallback_models: list[str] | None = None):
        super().__init__()
        self.model_name = model_name
        self.fallback_models = list(fallback_models or [])

    def _build_runtime_state(
        self,
        state: RuntimeStateMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any]:
        continuation = state.get("continuation")
        workflows = state.get("workflows") or []
        _ctx = runtime.context or {}
        continuation_active = bool(continuation) or _ctx.get("continue_trigger") == "continue"
        fallback_chain = _dedupe(
            [
                *self.fallback_models,
                *([EMBEDDED_BACKUP_MODEL_NAME] if embedded_backup_enabled() else []),
            ]
        )

        if workflows:
            workflow_resume_state = "resumed" if continuation_active else "loaded"
        else:
            workflow_resume_state = "fresh"

        continuation_source: str | None = None
        if continuation:
            continuation_source = continuation.get("source_title") or continuation.get("source_thread_id")
        elif _ctx.get("continue_trigger") == "continue":
            continuation_source = str(_ctx.get("continue_from_title") or _ctx.get("continue_from_thread_id") or "").strip() or None

        runtime_state = dict(state.get("runtime") or {})
        runtime_state.update(
            {
                "primary_model": self.model_name,
                "fallback_chain": fallback_chain,
                "fallback_ready": bool(fallback_chain),
                "embedded_backup_enabled": embedded_backup_enabled(),
                "continuation_source": continuation_source,
                "workflow_resume_state": workflow_resume_state,
                "memory_guard_state": _compute_memory_guard_state(),
                "updated_at": _utc_now(),
            }
        )
        governance = _ctx.get("session_governance")
        if isinstance(governance, dict):
            goal_drift = governance.get("goal_drift") or {}
            runtime_state["continuation_mode"] = governance.get("continuation_mode")
            context_pressure = governance.get("context_pressure")
            if context_pressure is not None:
                runtime_state["context_pressure"] = context_pressure
            recommended_memory_action = governance.get("recommended_memory_action")
            if recommended_memory_action is not None:
                runtime_state["recommended_memory_action"] = recommended_memory_action
            runtime_state["goal_drift_status"] = goal_drift.get("status")
        client_command = _ctx.get("client_command")
        if isinstance(client_command, dict):
            runtime_state["client_command_target"] = client_command.get("execution_target")
            runtime_state["planned_operation_id"] = client_command.get("operation_id")
        telemetry = get_model_runtime_telemetry()
        if telemetry is not None:
            runtime_state["active_model"] = telemetry.active_model or self.model_name
            runtime_state["fallback_switches"] = list(telemetry.fallback_switches)
            runtime_state["final_error"] = telemetry.final_error
        return runtime_state

    def _build_runtime_events(
        self,
        state: RuntimeStateMiddlewareState,
        runtime_state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        existing_events = list(state.get("workflow_events") or [])
        next_events = list(existing_events)

        fallback_switches = runtime_state.get("fallback_switches") or []
        for switch in fallback_switches:
            detail = f"{switch['from_model']} -> {switch['to_model']} because {switch['reason']}"
            if any(event.get("kind") == "fallback_switch" and event.get("detail") == detail for event in next_events):
                continue
            next_events.insert(
                0,
                _create_runtime_event(
                    "fallback_switch",
                    "Fallback switch triggered",
                    detail,
                    "warning",
                ),
            )

        active_model = runtime_state.get("active_model")
        if active_model and active_model != self.model_name:
            detail = f"Runtime continued on {active_model} instead of {self.model_name}."
            if not any(event.get("kind") == "runtime_degraded" and event.get("detail") == detail for event in next_events):
                next_events.insert(
                    0,
                    _create_runtime_event(
                        "runtime_degraded",
                        "Runtime is operating in degraded mode",
                        detail,
                        "warning",
                    ),
                )
        elif active_model and self.model_name:
            detail = f"Runtime is back on the primary model {self.model_name}."
            if not any(event.get("kind") == "primary_restored" and event.get("detail") == detail for event in next_events):
                next_events.insert(
                    0,
                    _create_runtime_event(
                        "primary_restored",
                        "Primary model restored",
                        detail,
                        "success",
                    ),
                )

        final_error = runtime_state.get("final_error")
        if final_error:
            detail = f"All runtime model candidates failed: {final_error}"
            if not any(event.get("kind") == "runtime_failed" and event.get("detail") == detail for event in next_events):
                next_events.insert(
                    0,
                    _create_runtime_event(
                        "runtime_failed",
                        "Runtime fallback chain failed",
                        detail,
                        "error",
                    ),
                )

        return next_events[:100]

    @override
    def before_agent(
        self,
        state: RuntimeStateMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        return {"runtime": self._build_runtime_state(state, runtime)}

    @override
    def before_model(
        self,
        state: RuntimeStateMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        del state, runtime
        begin_model_runtime_telemetry(self.model_name)
        return None

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        try:
            return handler(request)
        except Exception as exc:
            logger.exception("Model call failed; returning visible assistant error")
            return ModelResponse(result=[AIMessage(content=_runtime_failure_message(exc))])

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        try:
            return await handler(request)
        except Exception as exc:
            logger.exception("Async model call failed; returning visible assistant error")
            return ModelResponse(result=[AIMessage(content=_runtime_failure_message(exc))])

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        try:
            return handler(request)
        except Exception as exc:
            tool_name = request.tool.name if request.tool else request.tool_call.get("name", "unknown")
            logger.exception("Tool call failed; returning visible tool error: %s", tool_name)
            return ToolMessage(
                content=_runtime_failure_message(exc),
                tool_call_id=request.tool_call.get("id", "runtime-tool-error"),
                name=tool_name,
                status="error",
            )

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        try:
            return await handler(request)
        except Exception as exc:
            tool_name = request.tool.name if request.tool else request.tool_call.get("name", "unknown")
            logger.exception("Async tool call failed; returning visible tool error: %s", tool_name)
            return ToolMessage(
                content=_runtime_failure_message(exc),
                tool_call_id=request.tool_call.get("id", "runtime-tool-error"),
                name=tool_name,
                status="error",
            )

    @override
    async def abefore_model(
        self,
        state: RuntimeStateMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        return self.before_model(state, runtime)

    @override
    async def abefore_agent(
        self,
        state: RuntimeStateMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        return self.before_agent(state, runtime)

    @override
    def after_model(
        self,
        state: RuntimeStateMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        runtime_state = self._build_runtime_state(state, runtime)
        workflow_events = self._build_runtime_events(state, runtime_state)
        clear_model_runtime_telemetry()
        return {
            "runtime": runtime_state,
            "workflow_events": workflow_events,
        }

    @override
    async def aafter_model(
        self,
        state: RuntimeStateMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        return self.after_model(state, runtime)
