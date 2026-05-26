"""Inject a normalized instruction contract for the latest user turn."""

from __future__ import annotations

from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from src.agents.core.instruction_contracts import (
    build_contract_prompt,
    detect_instruction_contract,
)


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
