"""Inject a normalized instruction contract for the latest user turn."""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from src.agents.core.instruction_contracts import (
    build_contract_prompt,
    detect_instruction_contract,
)

_WEB_TOOL_NAMES = {"web_search", "web_fetch", "read_webpage", "scrapling_fetch", "scrapling_fetch_stealth", "tavily_search"}
_LOCAL_EXPLORATION_TOOL_NAMES = {
    "bash",
    "shell",
    "read_file",
    "list_dir",
    "glob",
    "grep",
    "search_files",
    "view_image",
}
_URL_RE = re.compile(r"https?://[^\s)\]}>'\"]+", re.IGNORECASE)


class InstructionContractMiddleware(AgentMiddleware[AgentState]):
    """Expose intent/evidence/risk rules to the model without UI leakage."""

    @override
    def before_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        del runtime
        messages = list(state.get("messages", []))
        if not messages:
            return None

        last_message = messages[-1]
        if not isinstance(last_message, HumanMessage):
            return None

        latest_text = str(last_message.content or "")
        contract = detect_instruction_contract(latest_text)
        if contract.intent == "general":
            return None

        contract_text = build_contract_prompt(contract)
        runtime_state = dict(state.get("runtime") or {})
        if isinstance(runtime_state, dict) and contract.require_runtime_identity:
            primary_model = runtime_state.get("primary_model") or "unknown"
            active_model = runtime_state.get("active_model") or primary_model
            contract_text += f"\n- Runtime identity:\n  - Primary model: {primary_model}\n  - Active model: {active_model}"

        contract_msg = SystemMessage(content=f"<instruction_contract>\n{contract_text}\n</instruction_contract>")
        messages.insert(-1, contract_msg)
        runtime_state["instruction_contract"] = {
            "intent": contract.intent,
            "risk_level": contract.risk_level,
            "requires_tool_evidence": contract.requires_tool_evidence,
            "required_tool_categories": list(contract.required_tool_categories),
            "required_domains": list(contract.required_domains),
            "min_evidence_links": contract.min_evidence_links,
            "requires_confirmation": contract.requires_confirmation,
            "guardrails": list(contract.guardrails),
        }
        return {"messages": messages, "runtime": runtime_state}

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        response = handler(request)
        return _repair_response_for_instruction_contract(response, request.messages, request.runtime.context or {})

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        response = await handler(request)
        return _repair_response_for_instruction_contract(response, request.messages, request.runtime.context or {})


def _latest_human_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage) or getattr(message, "type", "") == "human":
            content = getattr(message, "content", "")
            if isinstance(content, list):
                return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
            return str(content)
    return ""


def _instruction_contract_from_context(runtime_context: dict[str, Any]) -> dict[str, Any] | None:
    contract = runtime_context.get("instruction_contract")
    return contract if isinstance(contract, dict) else None


def _instruction_contract_from_messages(messages: list[Any]) -> dict[str, Any] | None:
    for message in reversed(messages):
        content = getattr(message, "content", "")
        if not isinstance(content, str) or "<instruction_contract>" not in content:
            continue
        intent = "current_research" if "Intent: current_research" in content else "general"
        required_tools: list[str] = []
        match = re.search(r"Required tool categories:\s*([^\n]+)", content)
        if match:
            required_tools = [item.strip() for item in match.group(1).split(",") if item.strip()]
        domains: list[str] = []
        match = re.search(r"User-named source domains to try first:\s*([^\n]+)", content)
        if match:
            domains = [item.strip() for item in match.group(1).split(",") if item.strip()]
        return {
            "intent": intent,
            "required_tool_categories": required_tools,
            "required_domains": domains,
        }
    return None


def _response_tool_calls(response: ModelResponse) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for message in response.result:
        if not isinstance(message, AIMessage) and getattr(message, "type", "") != "ai":
            continue
        for call in getattr(message, "tool_calls", None) or []:
            if isinstance(call, dict):
                calls.append(call)
    return calls


def _needs_research_tool_repair(
    response: ModelResponse,
    messages: list[Any],
    runtime_context: dict[str, Any],
) -> bool:
    contract = _instruction_contract_from_context(runtime_context) or _instruction_contract_from_messages(messages)
    if not contract or contract.get("intent") != "current_research":
        return False
    if "web" not in set(contract.get("required_tool_categories") or []):
        return False
    calls = _response_tool_calls(response)
    if not calls:
        return False
    names = {str(call.get("name") or "") for call in calls}
    if names & _WEB_TOOL_NAMES:
        return False
    return bool(names & _LOCAL_EXPLORATION_TOOL_NAMES) or bool(names)


def _build_source_first_web_call(user_text: str, runtime_context: dict[str, Any]) -> AIMessage:
    contract = _instruction_contract_from_context(runtime_context) or {}
    url_match = _URL_RE.search(user_text)
    if url_match:
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "id": f"repair_web_fetch_{uuid.uuid4().hex[:10]}",
                    "name": "web_fetch",
                    "args": {"url": url_match.group(0)},
                }
            ],
        )

    domains = [str(item).strip() for item in contract.get("required_domains") or [] if str(item).strip()]
    query = user_text.strip()
    if domains and not re.search(r"\bsite:", query, re.IGNORECASE):
        query = f"site:{domains[0]} {query}"
    return AIMessage(
        content="",
        tool_calls=[
            {
                "id": f"repair_web_search_{uuid.uuid4().hex[:10]}",
                "name": "web_search",
                "args": {"query": query},
            }
        ],
    )


def _repair_response_for_instruction_contract(
    response: ModelResponse,
    messages: list[Any],
    runtime_context: dict[str, Any],
) -> ModelResponse:
    if not _needs_research_tool_repair(response, messages, runtime_context):
        return response
    parsed_contract = _instruction_contract_from_context(runtime_context) or _instruction_contract_from_messages(messages) or {}
    repaired = _build_source_first_web_call(_latest_human_text(messages), {"instruction_contract": parsed_contract})
    return ModelResponse(result=[repaired], structured_response=response.structured_response)
