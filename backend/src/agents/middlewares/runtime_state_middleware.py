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
from src.models.runtime_telemetry import (
    begin_model_runtime_telemetry,
    clear_model_runtime_telemetry,
    get_model_runtime_telemetry,
)
from src.runtime.config.subagents_config import get_subagents_app_config
from src.utils.datetime import utc_now_iso as _utc_now

logger = logging.getLogger(__name__)
RUN_EVENT_LIMIT = 120
RUN_EVENT_KINDS = {
    "queued",
    "planning",
    "tool_call",
    "tool_result",
    "workflow",
    "subagent",
    "answer_delta",
    "artifact",
    "done",
    "error",
}
RUN_EVENT_LEVELS = {"info", "success", "warning", "error"}


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


def _create_run_event(
    *,
    kind: str,
    title: str,
    detail: str | None = None,
    level: str = "info",
    run_id: str | None = None,
    node_id: str | None = None,
    task_id: str | None = None,
    payload: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    timestamp = _utc_now()
    event: dict[str, Any] = {
        "id": event_id or f"run-event-{timestamp}",
        "kind": kind if kind in RUN_EVENT_KINDS else "planning",
        "title": title,
        "createdAt": timestamp,
        "level": level if level in RUN_EVENT_LEVELS else "info",
    }
    if detail:
        event["detail"] = detail
    if run_id:
        event["runId"] = run_id
    if node_id:
        event["nodeId"] = node_id
    if task_id:
        event["taskId"] = task_id
    if payload:
        event["payload"] = payload
    return event


def _normalize_run_event(event: Any) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    payload = event.get("event") if event.get("type") == "run_event" and isinstance(event.get("event"), dict) else event
    kind = payload.get("kind")
    if kind not in RUN_EVENT_KINDS:
        return None
    event_id = payload.get("id")
    created_at = payload.get("createdAt") or payload.get("created_at") or _utc_now()
    title = payload.get("title")
    normalized: dict[str, Any] = {
        "id": str(event_id or f"run-event-{created_at}"),
        "kind": kind,
        "title": str(title or kind.replace("_", " ").title()),
        "createdAt": str(created_at),
        "level": payload.get("level") if payload.get("level") in RUN_EVENT_LEVELS else "info",
    }
    for source_key, target_key in (
        ("detail", "detail"),
        ("runId", "runId"),
        ("run_id", "runId"),
        ("nodeId", "nodeId"),
        ("node_id", "nodeId"),
        ("taskId", "taskId"),
        ("task_id", "taskId"),
    ):
        value = payload.get(source_key)
        if value is not None and target_key not in normalized:
            normalized[target_key] = str(value)
    if isinstance(payload.get("payload"), dict):
        normalized["payload"] = payload["payload"]
    return normalized


def _run_event_key(event: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(event.get("id") or ""),
        str(event.get("kind") or ""),
        str(event.get("taskId") or ""),
        str(event.get("title") or ""),
        str(event.get("detail") or ""),
    )


def _merge_run_events(existing: list[Any], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for raw in [*reversed(additions), *existing]:
        event = _normalize_run_event(raw)
        if event is None:
            continue
        key = _run_event_key(event)
        if key in seen:
            continue
        seen.add(key)
        merged.append(event)
    return merged[:RUN_EVENT_LIMIT]


def _message_text_preview(value: Any, *, limit: int = 180) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value
    elif isinstance(value, list):
        parts: list[str] = []
        for part in value:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        text = " ".join(parts)
    else:
        text = str(value)
    text = text.strip().replace("\n", " ")
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _synthesize_run_events_from_messages(messages: list[Any], *, run_id: str | None = None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                if not isinstance(call, dict):
                    continue
                tool_name = str(call.get("name") or "tool")
                task_id = str(call.get("id") or f"tool-{index}")
                events.append(
                    _create_run_event(
                        kind="tool_call",
                        title=f"Calling {tool_name}",
                        detail=_message_text_preview(call.get("args")),
                        run_id=run_id,
                        task_id=task_id,
                        payload={"tool": tool_name},
                        event_id=f"run-event-tool-call-{task_id}",
                    )
                )
        if isinstance(message, ToolMessage) or getattr(message, "type", None) == "tool":
            task_id = str(getattr(message, "tool_call_id", "") or getattr(message, "id", "") or f"tool-result-{index}")
            tool_name = str(getattr(message, "name", "") or "tool")
            status = str(getattr(message, "status", "") or "").lower()
            is_error = status == "error"
            events.append(
                _create_run_event(
                    kind="error" if is_error else "tool_result",
                    title=f"{tool_name} failed" if is_error else f"{tool_name} finished",
                    detail=_message_text_preview(getattr(message, "content", None)),
                    level="error" if is_error else "success",
                    run_id=run_id,
                    task_id=task_id,
                    payload={"tool": tool_name},
                    event_id=f"run-event-tool-result-{task_id}",
                )
            )
    return events


def _control_run_event_from_context(context: dict[str, Any]) -> dict[str, Any] | None:
    raw = context.get("client_control_event")
    if not isinstance(raw, dict):
        return None
    action = str(raw.get("action") or "").strip().lower()
    if action not in {"retry", "resume", "stop"}:
        return None
    title_by_action = {
        "retry": "User retried the last turn",
        "resume": "User resumed the run",
        "stop": "User stopped the run",
    }
    return _create_run_event(
        kind="planning",
        title=str(raw.get("title") or title_by_action[action]),
        detail=_message_text_preview(raw.get("detail")),
        level="warning" if action == "stop" else "info",
        run_id=str(context.get("thread_id") or "") or None,
        payload={"controlAction": action},
        event_id=str(raw.get("id") or f"run-event-control-{action}-{_utc_now()}"),
    )


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

    def __init__(
        self,
        model_name: str | None,
        fallback_models: list[str] | None = None,
        *,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
    ):
        super().__init__()
        self.model_name = model_name
        self.fallback_models = list(fallback_models or [])
        self.thinking_enabled = thinking_enabled
        self.reasoning_effort = reasoning_effort

    def _build_runtime_state(
        self,
        state: RuntimeStateMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any]:
        continuation = state.get("continuation")
        workflows = state.get("workflows") or []
        _ctx = runtime.context or {}
        continuation_active = bool(continuation) or _ctx.get("continue_trigger") == "continue"
        fallback_chain = _dedupe(self.fallback_models)

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
                "continuation_source": continuation_source,
                "workflow_resume_state": workflow_resume_state,
                "memory_guard_state": _compute_memory_guard_state(),
                "thinking_enabled": self.thinking_enabled,
                "reasoning_effort": self.reasoning_effort,
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
        additions = _synthesize_run_events_from_messages(
            list(state.get("messages") or []),
            run_id=str(_ctx.get("thread_id") or "") or None,
        )
        control_event = _control_run_event_from_context(_ctx)
        if control_event is not None:
            additions.append(control_event)
        runtime_state["run_events"] = _merge_run_events(
            list(runtime_state.get("run_events") or []),
            additions,
        )
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
