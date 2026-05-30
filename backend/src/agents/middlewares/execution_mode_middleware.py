"""Execution-mode contract middleware.

This middleware gives the model a small, explicit operating contract for the
current turn. It separates two behaviors that otherwise get blurred:

* assisted mode: keep the user in the loop and ask promptly when a choice,
  credential, approval, or missing business input blocks correctness;
* goal-autopilot mode: work through failures with deliberate strategy changes
  before declaring the task impossible.
"""

from __future__ import annotations

from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from src.agents.dialogue_routing import ROUTE_CONTROL_COMMAND, ROUTE_DIRECT_ANSWER, ROUTE_PLAN_ONLY, classify_dialogue_route

_MARKER = '<execution_mode_contract origin="execution_mode_middleware"'

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
    """Resolve the behavioral mode for the current turn."""

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
        f'{_MARKER} mode="{mode}" route="{route}">',
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


class ExecutionModeMiddleware(AgentMiddleware[AgentState]):
    """Inject execution-mode context before the latest user turn."""

    @override
    def before_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        messages = list(state.get("messages", []))
        if not messages:
            return None
        if any(isinstance(message, SystemMessage) and _MARKER in str(message.content or "") for message in messages):
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


__all__ = ["ExecutionModeMiddleware", "build_execution_mode_contract", "resolve_execution_mode"]
