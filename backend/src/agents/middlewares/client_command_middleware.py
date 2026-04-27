"""Middleware that injects a server-approved client execution contract."""

from __future__ import annotations

from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime


class ClientCommandMiddleware(AgentMiddleware[AgentState]):
    """Expose normalized client intent as hidden context before the agent runs."""

    @override
    def before_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        client_command = (runtime.context or {}).get("client_command")
        governance = (runtime.context or {}).get("session_governance")
        if not isinstance(client_command, dict):
            return None

        messages = list(state.get("messages", []))
        if not messages:
            return None
        last_message = messages[-1]
        if not isinstance(last_message, HumanMessage):
            return None

        contract_lines = ["<client_execution_contract>"]
        contract_lines.append(
            "Client translated the latest user turn into a normalized operation contract. "
            "Server remains authoritative for approval, sandboxing, execution, and final output."
        )
        contract_lines.append(f"Operation ID: {client_command.get('operation_id', 'unknown')}")
        contract_lines.append(f"Intent: {client_command.get('intent', 'conversation')}")
        contract_lines.append(f"Execution target: {client_command.get('execution_target', 'repo_read')}")
        if client_command.get("cli_scope"):
            contract_lines.append(f"CLI scope: {client_command['cli_scope']}")
        if client_command.get("command_text"):
            contract_lines.append(f"Requested command: {client_command['command_text']}")
        if client_command.get("requested_url"):
            contract_lines.append(f"Requested URL: {client_command['requested_url']}")
        if client_command.get("requested_path"):
            contract_lines.append(f"Requested path: {client_command['requested_path']}")
        if client_command.get("requested_app"):
            contract_lines.append(f"Requested app: {client_command['requested_app']}")
        notes = client_command.get("notes") or []
        if isinstance(notes, list) and notes:
            contract_lines.append("Client notes:")
            contract_lines.extend(f"- {note}" for note in notes)

        if isinstance(governance, dict):
            goal_drift = governance.get("goal_drift") or {}
            contract_lines.append(f"Continuation mode: {governance.get('continuation_mode', 'fresh')}")
            contract_lines.append(f"Context pressure: {governance.get('context_pressure', 'low')}")
            contract_lines.append(
                f"Recommended memory action: {governance.get('recommended_memory_action', 'continue')}"
            )
            contract_lines.append(f"Goal drift status: {goal_drift.get('status', 'aligned')}")
            if goal_drift.get("reason"):
                contract_lines.append(f"Goal drift reason: {goal_drift['reason']}")
            if governance.get("continuity_summary"):
                contract_lines.append(f"Continuation summary: {governance['continuity_summary']}")
        contract_lines.append("</client_execution_contract>")

        # Insert contract as a SystemMessage before the last HumanMessage
        # instead of mutating the HumanMessage content (which would leak
        # the raw XML into the chat stream visible to the user).
        contract_msg = SystemMessage(content="\n".join(contract_lines))
        messages.insert(-1, contract_msg)
        return {"messages": messages}