"""AgentCore runtime facade for workflow-bound agent lifecycle operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.hook_core import get_hook_core_service

if TYPE_CHECKING:
    from src.query_engine import QuerySession
    from src.workflow_core import CreateAgentMessageRequest, TaskWorkspace


class AgentCoreService:
    """Stable boundary for task-scoped agent lifecycle and runtime actions."""

    def __init__(self):
        from src.workflow_core import get_workflow_core_service

        self._workflow = get_workflow_core_service()

    def _task_service(self, task_service=None):
        if task_service is not None:
            return task_service
        delegate = getattr(self._workflow, "_delegate", None)
        return delegate if delegate is not None else self._workflow

    def list_task_agents(self, task_id: str) -> list:
        workspace = self._workflow.get_workspace(task_id)
        return list(workspace.agents) if workspace is not None else []

    def get_task_agent(self, task_id: str, agent_id: str):
        workspace = self._workflow.get_workspace(task_id)
        if workspace is None:
            return None
        return next((agent for agent in workspace.agents if agent.agent_id == agent_id), None)

    def get_task_agent_context(self, task_id: str, agent_id: str):
        workspace = self._workflow.get_workspace(task_id)
        if workspace is None:
            return None, None
        agent = next((item for item in workspace.agents if item.agent_id == agent_id), None)
        return workspace, agent

    def list_agent_messages(self, task_id: str, agent_id: str):
        return self._workflow.list_agent_messages(task_id, agent_id)

    async def execute_agent_message(
        self,
        task_id: str,
        agent_id: str,
        request: CreateAgentMessageRequest,
    ):
        from src.workflow_core import execute_agent_message

        return await execute_agent_message(task_id, agent_id, request)

    def ensure_handoff_sessions(
        self,
        task_id: str,
        agent_ids: list[str] | None = None,
        *,
        task_service=None,
    ):
        service = self._task_service(task_service)
        workspace = service.get_workspace(task_id)
        if workspace is None:
            return None

        from src.query_engine import get_query_engine_service

        service._agent_lifecycle.ensure_handoff_sessions(
            workspace,
            agent_ids=agent_ids,
            query_service=get_query_engine_service(),
            create_handoff_session=lambda current_task_id, current_agent_id: self.create_agent_handoff_session(
                current_task_id,
                current_agent_id,
                task_service=service,
            ),
        )
        return service.get_workspace(task_id)

    def create_agent_handoff_session(
        self,
        task_id: str,
        agent_id: str,
        *,
        task_service=None,
    ) -> QuerySession | None:
        from src.orchestration import get_orchestration_service
        from src.query_engine import get_query_engine_service

        service = self._task_service(task_service)
        prompt_stack = get_orchestration_service().list_prompt_stacks()[0]
        session = service._agent_lifecycle.create_handoff_session(
            task_id,
            agent_id,
            update_workspace_record=service._update_workspace_record,
            progress_for_workspace=service._runtime_state.progress,
            query_service=get_query_engine_service(),
            prompt_stack=prompt_stack,
        )
        if session is not None:
            service._append_run_log(
                task_id,
                "Agent handoff session created",
                f"Agent ID: `{agent_id}`",
                f"Session ID: `{session.session_id}`",
            )
            get_hook_core_service().emit_handoff_created(task_id, agent_id, session.session_id)
        return session

    def dispatch_execution_started(
        self,
        task_id: str,
        agent_id: str,
        *,
        query_session_id: str | None = None,
        runtime_provider: str | None = None,
    ) -> None:
        hook_svc = get_hook_core_service()
        hook_svc.emit_execution_started(
            task_id,
            agent_id,
            query_session_id=query_session_id,
            runtime_provider=runtime_provider,
            status="running",
        )
        hook_svc.emit_agent_status_changed(task_id, agent_id, "running")

    def dispatch_agent_status_changed(self, task_id: str, agent_id: str, status: str) -> None:
        get_hook_core_service().emit_agent_status_changed(task_id, agent_id, status)

    def dispatch_execution_completed_event(
        self,
        task_id: str,
        *,
        source: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        get_hook_core_service().emit_execution_completed(task_id, source=source, payload=payload)

    def set_task_status(
        self,
        task_id: str,
        status: str,
        *,
        task_service=None,
    ) -> TaskWorkspace | None:
        service = self._task_service(task_service)
        if hasattr(service, "set_task_status"):
            return service.set_task_status(task_id, status)
        return self._workflow.set_task_status(task_id, status)

    def _write_agent_status(
        self,
        task_id: str,
        agent_id: str,
        status: str,
        *,
        task_service=None,
    ) -> TaskWorkspace | None:
        service = self._task_service(task_service)
        if hasattr(service, "set_agent_status"):
            return service.set_agent_status(task_id, agent_id, status)
        return self._workflow.set_agent_status(task_id, agent_id, status)

    def mark_workspace_running(self, task_id: str, *, task_service=None) -> TaskWorkspace | None:
        return self.set_task_status(task_id, "running", task_service=task_service)

    def _workspace_lifecycle_agents(self, task_id: str) -> list:
        get_workspace = getattr(self._workflow, "get_workspace", None)
        if not callable(get_workspace):
            return []
        workspace = get_workspace(task_id)
        if workspace is None:
            return []
        return list(workspace.agents)

    def pause_workspace_execution(self, task_id: str, *, task_service=None) -> TaskWorkspace | None:
        workspace: TaskWorkspace | None = None
        for agent in self._workspace_lifecycle_agents(task_id):
            if agent.status not in {"queued", "running", "waiting_handoff"}:
                continue
            workspace = self.set_agent_status(
                task_id,
                agent.agent_id,
                "paused",
                task_service=task_service,
            ) or workspace
        return self.set_task_status(task_id, "paused", task_service=task_service) or workspace

    def resume_workspace_execution(self, task_id: str, *, task_service=None) -> TaskWorkspace | None:
        workspace: TaskWorkspace | None = None
        for agent in self._workspace_lifecycle_agents(task_id):
            if agent.status != "paused":
                continue
            workspace = self.set_agent_status(
                task_id,
                agent.agent_id,
                "running",
                task_service=task_service,
            ) or workspace
        return self.set_task_status(task_id, "running", task_service=task_service) or workspace

    def terminate_workspace_execution(self, task_id: str, *, task_service=None) -> TaskWorkspace | None:
        workspace: TaskWorkspace | None = None
        for agent in self._workspace_lifecycle_agents(task_id):
            if agent.status in {"completed", "failed", "terminated"}:
                continue
            workspace = self.set_agent_status(
                task_id,
                agent.agent_id,
                "terminated",
                task_service=task_service,
            ) or workspace
        return self.set_task_status(task_id, "terminated", task_service=task_service) or workspace

    def pause_agent_execution(
        self,
        task_id: str,
        agent_id: str,
        *,
        task_service=None,
    ) -> TaskWorkspace | None:
        return self.set_agent_status(task_id, agent_id, "paused", task_service=task_service)

    def resume_agent_execution(
        self,
        task_id: str,
        agent_id: str,
        *,
        task_service=None,
    ) -> TaskWorkspace | None:
        return self.set_agent_status(task_id, agent_id, "running", task_service=task_service)

    def terminate_agent_execution(
        self,
        task_id: str,
        agent_id: str,
        *,
        task_service=None,
    ) -> TaskWorkspace | None:
        return self.set_agent_status(task_id, agent_id, "terminated", task_service=task_service)

    def begin_workspace_execution(
        self,
        task_id: str,
        *,
        lead_agent_id: str,
        task_service=None,
    ) -> TaskWorkspace | None:
        """Mark task and lead agent as running through the AgentCore boundary."""
        service = self._task_service(task_service)

        workspace: TaskWorkspace | None = None
        if hasattr(service, "set_task_status"):
            workspace = service.set_task_status(task_id, "running")
        else:
            workspace = self._workflow.set_task_status(task_id, "running")

        workspace = self._write_agent_status(task_id, lead_agent_id, "running", task_service=service) or workspace

        self.dispatch_execution_started(task_id, lead_agent_id)
        return workspace

    def dispatch_execution_finished(
        self,
        task_id: str,
        agent_id: str,
        *,
        tool_call_count: int,
        runtime_provider: str | None,
        execution_target: str | None,
        used_direct_fallback: bool,
        used_url_fetch_fallback: bool,
        used_server_side_fallback: bool,
        forced_failure_message: bool,
        runtime_invocation_failed: bool,
        query_session_id: str | None = None,
        runtime_session_id: str | None = None,
    ) -> None:
        recovered_with_fallback = (
            not forced_failure_message
            and (
                used_direct_fallback
                or used_url_fetch_fallback
                or used_server_side_fallback
            )
        )
        unrecovered_runtime_failure = runtime_invocation_failed and not recovered_with_fallback

        if forced_failure_message or unrecovered_runtime_failure:
            execution_status = "failed"
            terminal_agent_status = "failed"
        elif recovered_with_fallback:
            execution_status = "simulated"
            terminal_agent_status = "completed"
        else:
            execution_status = "completed"
            terminal_agent_status = "completed"

        payload = {
            "task_id": task_id,
            "agent_id": agent_id,
            "query_session_id": query_session_id,
            "runtime_session_id": runtime_session_id,
            "tool_call_count": tool_call_count,
            "runtime_provider": runtime_provider,
            "execution_target": execution_target,
            "used_direct_fallback": used_direct_fallback,
            "used_url_fetch_fallback": used_url_fetch_fallback,
            "used_server_side_fallback": used_server_side_fallback,
            "forced_failure_message": forced_failure_message,
            "runtime_invocation_failed": runtime_invocation_failed,
            "status": execution_status,
        }

        self.dispatch_execution_completed_event(
            task_id,
            source="agent_core.runtime",
            payload=payload,
        )
        if execution_status == "failed":
            self.dispatch_task_failed_event(task_id, payload=payload)
        else:
            self.dispatch_task_completed_event(task_id, payload=payload)
        self.dispatch_agent_status_changed(task_id, agent_id, terminal_agent_status)

    def dispatch_task_completed_event(self, task_id: str, *, payload: dict[str, object] | None = None) -> None:
        get_hook_core_service().emit_task_completed(task_id, payload)

    def dispatch_task_failed_event(self, task_id: str, *, payload: dict[str, object] | None = None) -> None:
        get_hook_core_service().emit_task_failed(task_id, payload)

    def dispatch_agents_terminated_event(self, task_id: str, *, payload: dict[str, object] | None = None) -> None:
        get_hook_core_service().emit_agents_terminated(task_id, payload)

    def set_agent_status(
        self,
        task_id: str,
        agent_id: str,
        status: str,
        *,
        task_service=None,
    ) -> TaskWorkspace | None:
        result = self._write_agent_status(task_id, agent_id, status, task_service=task_service)
        if result is not None:
            self.dispatch_agent_status_changed(task_id, agent_id, status)
        return result

    def apply_workspace_execution_state(
        self,
        task_id: str,
        *,
        agent_statuses: dict[str, str],
        workspace_status: str,
        task_service=None,
    ) -> TaskWorkspace | None:
        for agent_id, status in agent_statuses.items():
            self._write_agent_status(task_id, agent_id, status, task_service=task_service)
        return self.set_task_status(task_id, workspace_status, task_service=task_service) or self._workflow.get_workspace(task_id)

    # ------------------------------------------------------------------
    # Named completion / failure batch helpers (Slice F)
    # ------------------------------------------------------------------

    def complete_all_agents(self, task_id: str, agent_ids: list[str], *, task_service=None) -> TaskWorkspace | None:
        """Mark all agents as completed and workspace as completed."""
        statuses = {aid: "completed" for aid in agent_ids}
        result = self.apply_workspace_execution_state(
            task_id,
            agent_statuses=statuses,
            workspace_status="completed",
            task_service=task_service,
        )
        self.dispatch_task_completed_event(task_id, payload={"agent_ids": agent_ids})
        return result

    def fail_execution(
        self,
        task_id: str,
        *,
        lead_agent_id: str,
        all_agent_ids: list[str],
        task_service=None,
    ) -> TaskWorkspace | None:
        """Mark lead agent as failed, others as terminated, workspace as failed."""
        statuses = {
            aid: ("failed" if aid == lead_agent_id else "terminated")
            for aid in all_agent_ids
        }
        result = self.apply_workspace_execution_state(
            task_id,
            agent_statuses=statuses,
            workspace_status="failed",
            task_service=task_service,
        )
        self.dispatch_task_failed_event(
            task_id,
            payload={"lead_agent_id": lead_agent_id, "agent_ids": all_agent_ids},
        )
        return result

    def terminate_all_agents(self, task_id: str, agent_ids: list[str], *, task_service=None) -> TaskWorkspace | None:
        """Mark all agents as terminated and workspace as failed (crash recovery)."""
        statuses = {aid: "terminated" for aid in agent_ids}
        result = self.apply_workspace_execution_state(
            task_id,
            agent_statuses=statuses,
            workspace_status="failed",
            task_service=task_service,
        )
        self.dispatch_agents_terminated_event(task_id, payload={"agent_ids": agent_ids})
        return result

    def update_agent(self, task_id: str, agent_id: str, request) -> TaskWorkspace | None:
        result = self._workflow.update_agent(task_id, agent_id, request)
        if result is not None:
            get_hook_core_service().emit_agent_updated(task_id, agent_id)
        return result


_service = AgentCoreService()


def get_agent_core_service() -> AgentCoreService:
    return _service


__all__ = ["AgentCoreService", "get_agent_core_service"]