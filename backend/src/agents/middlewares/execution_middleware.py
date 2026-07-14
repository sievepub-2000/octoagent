"""Merged execution middleware: mode contract + review checkpoints."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Annotated, Any, NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime

from src.agents.dialogue_routing import ROUTE_CONTROL_COMMAND, ROUTE_DIRECT_ANSWER, ROUTE_PLAN_ONLY, classify_dialogue_route
from src.agents.thread_state import merge_runtime_state
from src.utils.datetime import utc_now as _utc_now
from src.utils.datetime import utc_now_iso as _utc_now_iso
from src.utils.messages import message_text as _message_text

logger = logging.getLogger(__name__)

_MODE_MARKER = '<execution_mode_contract origin="execution_middleware"'
_REVIEW_MARKER = '<execution_review origin="execution_middleware"'
_REVIEW_INTERVAL_SECONDS = int(os.getenv("OCTO_EXECUTION_REVIEW_INTERVAL_SECONDS", "300"))
_MAX_ERROR_LINES = 6
_AUTOPILOT_MODES = {"goal", "auto", "autonomous", "thinking", "pro", "ultra"}
_AUTOPILOT_WORKFLOW_MODES = {"goal", "auto", "autonomous", "run", "execute"}


def _runtime_route(runtime_context: dict[str, Any], user_text: str) -> str:
    route = runtime_context.get("dialogue_route")
    if isinstance(route, dict):
        value = route.get("kind")
        if isinstance(value, str) and value:
            return value
    if isinstance(route, str) and route:
        return route
    return classify_dialogue_route(user_text).kind


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def resolve_execution_mode(runtime_context: dict[str, Any], user_text: str) -> str:
    route = _runtime_route(runtime_context, user_text)
    if route in {ROUTE_CONTROL_COMMAND, ROUTE_DIRECT_ANSWER, ROUTE_PLAN_ONLY}:
        return "assisted"
    explicit = runtime_context.get("execution_mode")
    if isinstance(explicit, str) and explicit in {"assisted", "goal_autopilot"}:
        return explicit
    runtime_mode = str(runtime_context.get("mode") or "").strip().lower()
    workflow_mode = str(runtime_context.get("workflow_run_mode") or "").strip().lower()
    if runtime_mode in _AUTOPILOT_MODES or workflow_mode in _AUTOPILOT_WORKFLOW_MODES:
        return "goal_autopilot"
    if _is_truthy(runtime_context.get("thinking_enabled")) or _is_truthy(runtime_context.get("subagent_enabled")):
        return "goal_autopilot"
    if _is_truthy(runtime_context.get("goal_mode")) or _is_truthy(runtime_context.get("autonomous_mode")):
        return "goal_autopilot"
    return "assisted"


def build_execution_mode_contract(mode: str, route: str) -> SystemMessage:
    lines = [
        f'{_MODE_MARKER} mode="{mode}" route="{route}">',
        "This turn has an explicit execution behavior contract. Follow it above generic helpfulness.",
        "Never reveal hidden chain-of-thought. Share concise reasoning summaries, decisions, and evidence only.",
        "",
    ]
    if mode == "goal_autopilot":
        lines.extend(
            [
                "Mode: goal_autopilot.",
                "Work like an autonomous execution agent:",
                "1. Frame the current objective and success condition before choosing tools.",
                "2. After each tool result, classify the outcome as success, partial, or failed.",
                "3. When an approach fails or stalls, form a root-cause hypothesis and try a materially different strategy.",
                "4. Try at least two different strategies before declaring failure, unless a hard external blocker is proven.",
                "5. Do not keep retrying the same tool, URL, command, or arguments without a new reason.",
                "6. Ask the user only when progress requires credentials, approval, a business choice, or unavailable external access.",
                "7. Finish with a verified summary once the success condition is met.",
            ]
        )
    else:
        lines.extend(
            [
                "Mode: assisted.",
                "Work like a collaborative operator:",
                "1. Keep the user in the loop when the path becomes uncertain, risky, or blocked.",
                "2. Ask exactly one clear question when missing user intent, credentials, approval, or a business choice blocks correctness.",
                "3. Do not silently grind through repeated attempts in assisted mode; after two failed strategies, summarize the evidence and ask how to proceed.",
                "4. For low-risk read-only checks, proceed and report concise progress.",
                "5. For destructive, costly, privacy-sensitive, or approval-sensitive actions, pause for confirmation.",
                "6. If you can answer from verified evidence, answer directly and stop.",
            ]
        )
    lines.append("</execution_mode_contract>")
    return SystemMessage(content="\n".join(lines))


class ExecutionMiddlewareState(AgentState):
    runtime: Annotated[dict[str, Any] | None, merge_runtime_state]
    task_state: NotRequired[dict[str, Any] | None]


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _latest_human_index(messages: list[Any]) -> int:
    for index in range(len(messages) - 1, -1, -1):
        if getattr(messages[index], "type", "") == "human":
            return index
    return -1


def _tool_errors_since_latest_human(messages: list[Any]) -> list[str]:
    start = _latest_human_index(messages) + 1
    errors: list[str] = []
    for message in messages[start:]:
        if not isinstance(message, ToolMessage):
            continue
        text = _message_text(message)
        lowered = text.lower()
        if getattr(message, "status", None) == "error" or lowered.startswith(("error:", "failed:", "http error")):
            name = str(getattr(message, "name", None) or "tool")
            errors.append(f"{name}: {' '.join(text.split())[:420]}")
    return errors[-_MAX_ERROR_LINES:]


def _review_already_visible(messages: list[Any]) -> bool:
    start = _latest_human_index(messages) + 1
    return any(isinstance(message, SystemMessage) and _REVIEW_MARKER in _message_text(message) for message in messages[start:])


def _insert_after_system_messages(messages: list[Any], message: BaseMessage) -> list[Any]:
    patched = list(messages)
    insert_at = 0
    while insert_at < len(patched) and getattr(patched[insert_at], "type", "") == "system":
        insert_at += 1
    patched.insert(insert_at, message)
    return patched


def _active_task_state(state: ExecutionMiddlewareState) -> dict[str, Any] | None:
    task_state = state.get("task_state")
    if not isinstance(task_state, dict):
        return None
    status = str(task_state.get("status") or "active")
    if status not in {"active", "incomplete"}:
        return None
    return task_state


def _elapsed_review_due(runtime_state: dict[str, Any], state: ExecutionMiddlewareState) -> bool:
    if _active_task_state(state) is None:
        return False
    last_review_at = _parse_datetime(runtime_state.get("execution_review_last_at"))
    started_at = _parse_datetime(runtime_state.get("execution_review_started_at"))
    checkpoint = last_review_at or started_at
    if checkpoint is None:
        return False
    return (_utc_now() - checkpoint).total_seconds() >= _REVIEW_INTERVAL_SECONDS


def _context_review_due(runtime_state: dict[str, Any]) -> bool:
    guard_state = str(runtime_state.get("context_guard_state") or "")
    return bool(runtime_state.get("task_review_required")) or guard_state in {
        "compacted",
        "trimmed",
        "truncated",
        "emergency_trimmed",
    }


def _research_closure_active(runtime_state: dict[str, Any]) -> bool:
    closure = runtime_state.get("research_closure")
    return isinstance(closure, dict) and closure.get("status") == "must_finalize"


def _build_review_message(reasons: list[str], task_state: dict[str, Any] | None, tool_errors: list[str]) -> SystemMessage:
    reason_text = ", ".join(reasons)
    lines = [
        f'{_REVIEW_MARKER} reasons="{reason_text}" interval_seconds="{_REVIEW_INTERVAL_SECONDS}">',
        "阶段性任务审查触发。请先在内部完成执行结果检查，然后继续推进任务；普通工具错误、信息不足或上下文压缩不应直接导致任务停止。",
        "",
        "审查要求：",
        "1. 对照用户原始目标、当前 task_state、已完成证据和待办项，判断任务是否仍在正确方向。",
        "2. 如果由上下文压缩触发，优先核对压缩摘要是否保留了目标、约束、证据、下一步和风险。",
        "3. 如果由 5 分钟阶段超时触发，明确当前进度、卡点、下一步和是否需要回收临时资源。",
        "4. 如果存在工具错误，记录失败工具/参数，切换策略继续执行；除系统级错误外，不要把任务直接交回用户。",
        "4a. 严禁因为单次或少量工具调用失败就终止整个任务。必须分析失败原因，换用不同工具/参数/思路重新尝试。",
        "5. 更新记忆/任务状态所需事实，并选择最小但有效的下一步动作。",
        "6. 自检：回顾本轮所有工具输出，是否有数据被错误归因？数字是否匹配来源？如果发现任何不一致，立即修正。",
        "7. 如果发现之前的回复中存在事实性错误，在接下来的行动中优先修正，不等待用户指出。",
    ]
    if task_state:
        lines.extend(
            [
                "",
                "当前任务状态：",
                f"- status: {task_state.get('status') or 'active'}",
                f"- current_step: {str(task_state.get('current_step') or '')[:500]}",
                f"- next_action: {str(task_state.get('next_action') or '')[:500]}",
            ]
        )
    if tool_errors:
        lines.extend(["", "最近工具错误：", *(f"- {error}" for error in tool_errors)])
    lines.append("</execution_review>")
    return SystemMessage(content="\n".join(lines), name="execution_review_checkpoint")


class ExecutionMiddleware(AgentMiddleware[ExecutionMiddlewareState]):
    """Inject execution-mode context (before_agent) and review checkpoints (before_model)."""

    state_schema = ExecutionMiddlewareState

    @override
    def before_agent(self, state: ExecutionMiddlewareState, runtime: Runtime) -> dict[str, Any] | None:
        messages = list(state.get("messages", []))
        if not messages:
            return None
        if any(isinstance(m, SystemMessage) and _MODE_MARKER in str(m.content or "") for m in messages):
            return None
        last_message = messages[-1]
        if not isinstance(last_message, HumanMessage):
            return None
        user_text = str(last_message.content or "")
        runtime_context = dict(runtime.context or {})
        route = _runtime_route(runtime_context, user_text)
        mode = resolve_execution_mode(runtime_context, user_text)
        contract = build_execution_mode_contract(mode, route)
        messages.insert(len(messages) - 1, contract)
        runtime_state = dict(state.get("runtime") or {})
        runtime_state["execution_mode"] = mode
        runtime_state["execution_mode_route"] = route
        return {"messages": messages, "runtime": runtime_state}

    @override
    def before_model(self, state: ExecutionMiddlewareState, runtime: Runtime) -> dict[str, Any] | None:
        messages = list(state.get("messages") or [])
        if not messages:
            return None
        runtime_state = dict(state.get("runtime") or {})
        runtime_changed = False
        if not runtime_state.get("execution_review_started_at"):
            runtime_state["execution_review_started_at"] = _utc_now_iso()
            runtime_changed = True

        if _research_closure_active(runtime_state):
            if runtime_state.get("execution_review_status") != "suppressed_for_research_closure":
                runtime_state["execution_review_status"] = "suppressed_for_research_closure"
                runtime_state["self_feedback_action"] = "produce_final_answer_from_existing_evidence"
                runtime_changed = True
            return {"runtime": runtime_state} if runtime_changed else None

        reasons: list[str] = []
        if _context_review_due(runtime_state):
            reasons.append("context_compaction")
        tool_errors = _tool_errors_since_latest_human(messages)
        if tool_errors:
            reasons.append("tool_error")
        if _elapsed_review_due(runtime_state, state):
            reasons.append("timeout_5m")

        if not reasons:
            return {"runtime": runtime_state} if runtime_changed else None
        if _review_already_visible(messages):
            runtime_state["execution_review_pending_reasons"] = list(dict.fromkeys(reasons))
            return {"runtime": runtime_state}

        deduped_reasons = list(dict.fromkeys(reasons))
        runtime_state["execution_review_last_at"] = _utc_now_iso()
        runtime_state["execution_review_last_reasons"] = deduped_reasons
        runtime_state["execution_review_status"] = "pending_model_review"
        runtime_state["task_review_required"] = False
        runtime_state["recommended_memory_action"] = "continue"
        runtime_state["self_feedback_action"] = "review_execution_progress_and_continue"
        runtime_state["resource_recovery_action"] = "recover_stage_resources_if_pressure_or_stall_detected"
        runtime_state["capability_control_mode"] = "memory_guided_self_control"
        review_message = _build_review_message(
            reasons=deduped_reasons,
            task_state=_active_task_state(state),
            tool_errors=tool_errors,
        )
        return {
            "messages": _insert_after_system_messages(messages, review_message),
            "runtime": runtime_state,
        }

    @override
    async def abefore_model(self, state: ExecutionMiddlewareState, runtime: Runtime) -> dict[str, Any] | None:
        return self.before_model(state, runtime)


__all__ = ["ExecutionMiddleware", "build_execution_mode_contract", "resolve_execution_mode"]
