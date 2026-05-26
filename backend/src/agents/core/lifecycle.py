"""Task-scoped agent lifecycle helpers reused by workflow-backed services."""

from __future__ import annotations

from collections.abc import Callable

from src.storage.query import QuerySession
from src.storage.task_workspaces.contracts import (
    AgentHandle,
    AgentMessage,
    CreateAgentMessageRequest,
    TaskWorkspace,
    UpdateAgentRequest,
    make_id,
    utc_now,
)


class AgentLifecycleFacade:
    """Encapsulate task-scoped agent lookup, messaging, and lifecycle mutations."""

    @staticmethod
    def find_agent(workspace: TaskWorkspace, agent_id: str) -> AgentHandle | None:
        return next((agent for agent in workspace.agents if agent.agent_id == agent_id), None)

    def create_handoff_session(
        self,
        task_id: str,
        agent_id: str,
        *,
        update_workspace_record: Callable[[str, Callable[[TaskWorkspace], TaskWorkspace | None]], TaskWorkspace | None],
        progress_for_workspace: Callable[[TaskWorkspace], object],
        query_service,
        prompt_stack,
    ) -> QuerySession | None:
        created_session: QuerySession | None = None

        def _create(workspace: TaskWorkspace) -> TaskWorkspace | None:
            nonlocal created_session
            agent = self.find_agent(workspace, agent_id)
            if agent is None:
                return None
            linked_card = next(
                (card for card in workspace.card_graph.cards if card.card_id == agent.linked_card_id),
                None,
            )
            permission_mode = linked_card.permission_mode if linked_card is not None else "workspace"
            created_session = query_service.create_workspace_session(
                workspace,
                agent,
                prompt_stack,
                created_at=utc_now(),
            )
            agent.status = "waiting_handoff"
            agent.metadata["query_session_id"] = created_session.session_id
            agent.metadata["permission_mode"] = permission_mode
            workspace.updated_at = utc_now()
            workspace.metadata["last_handoff_session_id"] = created_session.session_id
            workspace.progress = progress_for_workspace(workspace)
            return workspace

        updated = update_workspace_record(task_id, _create)
        if updated is None:
            return None
        return created_session

    def ensure_handoff_sessions(
        self,
        workspace: TaskWorkspace,
        *,
        agent_ids: list[str] | None,
        query_service,
        create_handoff_session: Callable[[str, str], QuerySession | None],
    ) -> None:
        target_ids = set(agent_ids or [agent.agent_id for agent in workspace.agents])
        for agent in workspace.agents:
            if agent.agent_id not in target_ids:
                continue
            session_id = str(agent.metadata.get("query_session_id") or "").strip()
            if session_id and query_service.get_session(session_id) is not None:
                continue
            create_handoff_session(workspace.task_id, agent.agent_id)

    def list_agent_messages(
        self,
        task_id: str,
        agent_id: str,
        *,
        find_workspace: Callable[[str], TaskWorkspace | None],
        list_messages: Callable[[str, str], list[AgentMessage]],
    ) -> list[AgentMessage] | None:
        workspace = find_workspace(task_id)
        if workspace is None or self.find_agent(workspace, agent_id) is None:
            return None
        return list_messages(task_id, agent_id)

    def append_agent_message(
        self,
        task_id: str,
        agent_id: str,
        request: CreateAgentMessageRequest,
        *,
        assistant_content: str | None,
        load_workspaces: Callable[[], list[TaskWorkspace]],
        persist_workspaces: Callable[[list[TaskWorkspace]], None],
        list_messages: Callable[[str, str], list[AgentMessage]],
        save_messages: Callable[[str, str, list[AgentMessage], str | None], None],
        progress_for_workspace: Callable[[TaskWorkspace], object],
        append_run_log: Callable[[str, str, str], None],
    ) -> list[AgentMessage] | None:
        workspaces = load_workspaces()
        target_workspace: TaskWorkspace | None = None
        target_agent: AgentHandle | None = None
        for workspace in workspaces:
            if workspace.task_id != task_id:
                continue
            target_workspace = workspace
            target_agent = self.find_agent(workspace, agent_id)
            break
        if target_workspace is None or target_agent is None:
            return None

        messages = list_messages(task_id, agent_id)
        timestamp = utc_now()
        messages.append(
            AgentMessage(
                message_id=make_id("message"),
                role="user",
                content=request.content,
                created_at=timestamp,
            )
        )
        response_text = assistant_content or (f"{target_agent.name} acknowledged the message. Live runtime chat handoff is not wired yet, so this message is stored in the task workspace transcript.")
        messages.append(
            AgentMessage(
                message_id=make_id("message"),
                role="assistant",
                content=response_text,
                created_at=utc_now(),
            )
        )
        save_messages(task_id, agent_id, messages, target_agent.name)
        target_agent.conversation.message_count = len(messages)
        target_agent.conversation.last_message_at = messages[-1].created_at
        target_workspace.updated_at = utc_now()
        target_workspace.progress = progress_for_workspace(target_workspace)
        persist_workspaces(workspaces)
        append_run_log(
            task_id,
            f"Agent message: {target_agent.name}",
            f"User: {request.content}",
            f"Assistant: {response_text}",
        )
        return messages

    def set_agent_status(
        self,
        task_id: str,
        agent_id: str,
        status: str,
        *,
        update_workspace_record: Callable[[str, Callable[[TaskWorkspace], TaskWorkspace | None]], TaskWorkspace | None],
        progress_for_workspace: Callable[[TaskWorkspace], object],
    ) -> TaskWorkspace | None:
        def _update(workspace: TaskWorkspace) -> TaskWorkspace | None:
            agent = self.find_agent(workspace, agent_id)
            if agent is None:
                return None
            agent.status = status  # type: ignore[assignment]
            workspace.updated_at = utc_now()
            workspace.progress = progress_for_workspace(workspace)
            return workspace

        return update_workspace_record(task_id, _update)

    def update_agent(
        self,
        task_id: str,
        agent_id: str,
        request: UpdateAgentRequest,
        *,
        update_workspace_record: Callable[[str, Callable[[TaskWorkspace], TaskWorkspace | None]], TaskWorkspace | None],
        progress_for_workspace: Callable[[TaskWorkspace], object],
    ) -> TaskWorkspace | None:
        def _update(workspace: TaskWorkspace) -> TaskWorkspace | None:
            agent = self.find_agent(workspace, agent_id)
            if agent is None:
                return None
            if request.name is not None:
                agent.name = request.name
            if request.role is not None:
                agent.role = request.role
            if request.model_name is not None:
                agent.model_name = request.model_name
            if request.task_scope is not None:
                agent.task_scope = request.task_scope
            if request.metadata is not None:
                agent.metadata.update(request.metadata)
            workspace.updated_at = utc_now()
            workspace.progress = progress_for_workspace(workspace)
            return workspace

        return update_workspace_record(task_id, _update)


__all__ = ["AgentLifecycleFacade"]
