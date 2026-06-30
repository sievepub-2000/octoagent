"""Workflow runtime helpers shared by gateway lifecycle and route adapters."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from src.agents.runtime import AgentExecutionRequest, get_agent_runtime_manager
from src.storage.query import QuerySession

from .contracts import AgentMessage, CreateAgentMessageRequest, TaskWorkspace
from .service import get_workflow_core_service, get_workflow_execution_controller, get_workflow_message_executor

logger = logging.getLogger(__name__)


def _runtime_hint(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _resolve_langgraph_thread_scope(workspace: TaskWorkspace | None) -> str:
    metadata = workspace.metadata if workspace is not None and isinstance(workspace.metadata, dict) else {}
    configured = _runtime_hint(metadata.get("langgraph_thread_scope"))
    if configured is not None:
        return configured
    if workspace is not None and workspace.mode in {"branch", "group"}:
        return "agent"
    return "workspace"


def _resolve_langgraph_assistant_id(workspace: TaskWorkspace | None, agent: Any | None) -> str:
    agent_metadata = agent.metadata if agent is not None and isinstance(agent.metadata, dict) else {}
    workspace_metadata = workspace.metadata if workspace is not None and isinstance(workspace.metadata, dict) else {}
    return _runtime_hint(agent_metadata.get("langgraph_assistant_id")) or _runtime_hint(workspace_metadata.get("langgraph_assistant_id")) or "lead_agent"


def _resolve_langgraph_graph_id(workspace: TaskWorkspace | None) -> str | None:
    if workspace is None or not isinstance(workspace.metadata, dict):
        return None
    return _runtime_hint(workspace.metadata.get("langgraph_graph_id")) or _runtime_hint(workspace.metadata.get("compiled_graph_id"))


def _resolve_langgraph_thread_id(workspace: TaskWorkspace | None, agent: Any | None) -> str | None:
    thread_scope = _resolve_langgraph_thread_scope(workspace)
    agent_metadata = agent.metadata if agent is not None and isinstance(agent.metadata, dict) else {}
    workspace_metadata = workspace.metadata if workspace is not None and isinstance(workspace.metadata, dict) else {}

    if thread_scope == "agent":
        return _runtime_hint(agent_metadata.get("runtime_session_id")) or _runtime_hint(agent_metadata.get("langgraph_thread_id"))

    return (
        _runtime_hint(agent_metadata.get("runtime_session_id"))
        or _runtime_hint(agent_metadata.get("langgraph_thread_id"))
        or _runtime_hint(workspace_metadata.get("last_runtime_session_id"))
        or _runtime_hint(workspace_metadata.get("langgraph_thread_id"))
    )


async def invoke_agent_runtime(
    task_id: str,
    prompt: str,
    *,
    workspace: TaskWorkspace | None = None,
    agent: Any | None = None,
    model_override: str | None,
    timeout_seconds: int,
    recursion_limit: int,
    subagent_enabled: bool,
    query_session_id: str | None = None,
    agent_runtime_provider_override: str | None = None,
) -> tuple[str | None, int, str | None, str | None, str, dict[str, Any]]:
    workspace_metadata = dict((workspace.metadata if workspace is not None else {}) or {})
    if workspace is not None:
        workspace_metadata.setdefault("workflow_mode", workspace.mode)
        workspace_metadata.setdefault("langgraph_thread_scope", _resolve_langgraph_thread_scope(workspace))

    result = await get_agent_runtime_manager().execute(
        AgentExecutionRequest(
            task_id=task_id,
            prompt=prompt,
            model_override=model_override,
            timeout_seconds=timeout_seconds,
            recursion_limit=recursion_limit,
            subagent_enabled=subagent_enabled,
            query_session_id=query_session_id,
            workspace_metadata=workspace_metadata,
            agent_id=getattr(agent, "agent_id", None),
            agent_name=getattr(agent, "name", None),
            agent_role=getattr(agent, "role", None),
            assistant_id=_resolve_langgraph_assistant_id(workspace, agent),
            thread_id=_resolve_langgraph_thread_id(workspace, agent),
            graph_id=_resolve_langgraph_graph_id(workspace),
            agent_runtime_provider_override=agent_runtime_provider_override,
        ),
        workspace=workspace,
    )
    return (
        result.output_text,
        result.tool_call_count,
        result.thread_id,
        result.planned_execution_target,
        result.provider,
        result.raw,
    )


async def invoke_langgraph_assistant(
    task_id: str,
    prompt: str,
    *,
    workspace: TaskWorkspace | None = None,
    model_override: str | None,
    timeout_seconds: int,
    recursion_limit: int,
    subagent_enabled: bool,
    query_session_id: str | None = None,
) -> tuple[str | None, int, str | None, str | None, str]:
    return await invoke_agent_runtime(
        task_id,
        prompt,
        workspace=workspace,
        agent=None,
        model_override=model_override,
        timeout_seconds=timeout_seconds,
        recursion_limit=recursion_limit,
        subagent_enabled=subagent_enabled,
        query_session_id=query_session_id,
    )


async def execute_agent_message(
    task_id: str,
    agent_id: str,
    request: CreateAgentMessageRequest,
) -> list[AgentMessage] | None:
    from src.agents.core import get_agent_core_service
    from src.storage.project.service import get_project_service

    service = get_workflow_core_service()
    workspace = service.get_workspace(task_id) if hasattr(service, "get_workspace") else None
    workspace = get_agent_core_service().ensure_handoff_sessions(task_id, [agent_id]) or workspace
    return await get_workflow_message_executor().execute(
        task_id=task_id,
        agent_id=agent_id,
        request=request,
        workspace=workspace,
        invoke_agent_runtime=invoke_agent_runtime,
        append_message=service.append_agent_message,
    )


def has_agent_messages(workspace: TaskWorkspace) -> bool:
    service = get_workflow_core_service()
    for agent in workspace.agents:
        messages = service.list_agent_messages(workspace.task_id, agent.agent_id) or []
        if messages:
            return True
    return False


async def safe_auto_execute_lead_agent(
    workspace: TaskWorkspace,
    *,
    merge_workspace_metadata,
    workflow_module_factory,
) -> None:
    if not workspace.agents:
        return

    async def _send_message(task_id: str, agent_id: str, request: CreateAgentMessageRequest):
        messages = await execute_agent_message(task_id, agent_id, request)
        return SimpleNamespace(messages=messages or [])

    await get_workflow_execution_controller().safe_auto_execute_workspace(
        workspace,
        send_message=_send_message,
        service_getter=get_workflow_core_service,
        merge_workspace_metadata=merge_workspace_metadata,
        workflow_module_factory=workflow_module_factory,
    )


# Provider-neutral alias (preferred); safe_auto_execute_lead_agent is deprecated
safe_auto_execute_workspace = safe_auto_execute_lead_agent


def recoverable_orphaned_workspaces() -> list[TaskWorkspace]:
    service = get_workflow_core_service()
    return [workspace for workspace in service.list_workspaces() if workspace.status == "running" and not has_agent_messages(workspace)]


__all__ = [
    "AgentMessage",
    "execute_agent_message",
    "QuerySession",
    "has_agent_messages",
    "invoke_agent_runtime",
    "invoke_langgraph_assistant",
    "recoverable_orphaned_workspaces",
    "safe_auto_execute_lead_agent",
    "safe_auto_execute_workspace",
]
