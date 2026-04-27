"""Authoritative task-backed workflow module for task workspaces."""

from __future__ import annotations

from typing import Any

from src.workflow_core.status import workflow_stage_for_status

from .contracts import TaskWorkspace
from .workflow_files import WorkflowFileManager

WORKFLOW_MODULE_VERSION = "task-workflow-v2"


class TaskWorkflowModule:
    """Project task workspace state into the canonical task/workflow directory."""

    def __init__(self, file_manager: WorkflowFileManager | None = None) -> None:
        self._files = file_manager or WorkflowFileManager()

    def initialize(
        self,
        workspace: TaskWorkspace,
        *,
        event_title: str | None = None,
        event_details: list[str] | None = None,
    ) -> dict[str, Any]:
        if self._files.get_dir_path(workspace.task_id) is None:
            self._files.create_workflow_dir(
                workflow_id=workspace.task_id,
                name=workspace.name,
                goal=workspace.goal,
                mode=workspace.mode,
                agent_runtime_provider=workspace.agent_runtime_provider,
                summary=workspace.summary,
                main_agent=self._main_agent_name(workspace),
                sub_agents=self._sub_agent_names(workspace),
                agents=[agent.model_dump(mode="json") for agent in workspace.agents],
                cards=[card.model_dump(mode="json") for card in workspace.card_graph.cards],
                edges=[edge.model_dump(mode="json") for edge in workspace.card_graph.edges],
                status=workspace.status,
            )
        return self.sync_workspace(
            workspace,
            event_title=event_title,
            event_details=event_details,
        )

    def sync_workspace(
        self,
        workspace: TaskWorkspace,
        *,
        event_title: str | None = None,
        event_details: list[str] | None = None,
    ) -> dict[str, Any]:
        self._files.update_task_file(
            workspace.task_id,
            name=workspace.name,
            goal=workspace.goal,
            mode=workspace.mode,
            agent_runtime_provider=workspace.agent_runtime_provider,
            summary=workspace.summary,
            main_agent=self._main_agent_name(workspace),
            sub_agents=self._sub_agent_names(workspace),
        )
        if event_title is not None:
            self._files.append_run_log(
                workspace.task_id,
                title=event_title,
                details=list(event_details or []),
            )
        self._files.update_workflow_file(
            workspace.task_id,
            name=workspace.name,
            goal=workspace.goal,
            mode=workspace.mode,
            agent_runtime_provider=workspace.agent_runtime_provider,
            agents=[agent.model_dump(mode="json") for agent in workspace.agents],
            cards=[card.model_dump(mode="json") for card in workspace.card_graph.cards],
            edges=[edge.model_dump(mode="json") for edge in workspace.card_graph.edges],
            status=workspace.status,
        )
        snapshot = self._build_snapshot(workspace)
        self._files.write_workflow_state(workspace.task_id, snapshot)
        document_paths = self._files.document_paths(workspace.task_id)
        return {
            "workflow_dir": snapshot["task_dir"],
            "task_dir": snapshot["task_dir"],
            "workflow_stage": snapshot["stage"],
            "workflow_module_name": "task",
            "workflow_module_version": WORKFLOW_MODULE_VERSION,
            "project_doc_path": document_paths["project"],
            "workflow_doc_path": document_paths["settings"],
            "result_doc_path": document_paths["result"],
        }

    def record_execution_result(
        self,
        workspace: TaskWorkspace,
        *,
        status: str,
        output: str,
        transcripts: str,
        failure_reason: str | None,
    ) -> list[dict[str, str]]:
        artifacts = self._files.sync_task_attachments(workspace.task_id)
        self._files.update_result_file(
            workspace.task_id,
            name=workspace.name,
            status=status,
            output=output,
            transcripts=transcripts,
            artifacts=artifacts,
            failure_reason=failure_reason,
        )
        self._files.update_workflow_file(
            workspace.task_id,
            name=workspace.name,
            goal=workspace.goal,
            mode=workspace.mode,
            agent_runtime_provider=workspace.agent_runtime_provider,
            agents=[agent.model_dump(mode="json") for agent in workspace.agents],
            cards=[card.model_dump(mode="json") for card in workspace.card_graph.cards],
            edges=[edge.model_dump(mode="json") for edge in workspace.card_graph.edges],
            status=status,
        )
        snapshot = self._build_snapshot(
            workspace,
            status=status,
            artifacts=artifacts,
            result={
                "status": status,
                "failure_reason": failure_reason,
            },
        )
        self._files.write_workflow_state(workspace.task_id, snapshot)
        return artifacts

    def delete(self, task_id: str) -> None:
        self._files.delete_workflow_dir(task_id)

    def get_dir_path(self, task_id: str) -> str | None:
        return self._files.get_dir_path(task_id)

    def _build_snapshot(
        self,
        workspace: TaskWorkspace,
        *,
        status: str | None = None,
        artifacts: list[dict[str, str]] | None = None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_status = status or workspace.status
        task_dir = self._files.get_dir_path(workspace.task_id) or ""
        resolved_artifacts = list(artifacts) if artifacts is not None else self._files.sync_task_attachments(workspace.task_id)
        document_paths = self._files.document_paths(workspace.task_id)
        builder_state = workspace.metadata.get("brain_builder_state")
        builder_snapshot = builder_state if isinstance(builder_state, dict) else {}
        try:
            from src.agent_runtime import get_langgraph_workflow_contract_service

            langgraph_contract = get_langgraph_workflow_contract_service().contract_for_task(workspace.task_id)
        except Exception:
            langgraph_contract = {"task_id": workspace.task_id, "threads": [], "summary": {}}
        return {
            "module_version": WORKFLOW_MODULE_VERSION,
            "workflow_name": "task",
            "task_id": workspace.task_id,
            "task_name": workspace.name,
            "task_dir": task_dir,
            "mode": workspace.mode,
            "agent_runtime_provider": workspace.agent_runtime_provider,
            "status": resolved_status,
            "stage": workflow_stage_for_status(resolved_status),
            "goal": workspace.goal,
            "summary": workspace.summary,
            "created_at": workspace.created_at,
            "updated_at": workspace.updated_at,
            "main_agent": self._main_agent_name(workspace),
            "sub_agents": self._sub_agent_names(workspace),
            "agents": [agent.model_dump(mode="json") for agent in workspace.agents],
            "cards": [card.model_dump(mode="json") for card in workspace.card_graph.cards],
            "edges": [edge.model_dump(mode="json") for edge in workspace.card_graph.edges],
            "checkpoints": [checkpoint.model_dump(mode="json") for checkpoint in workspace.checkpoints],
            "langgraph_contract": langgraph_contract,
            "artifacts": resolved_artifacts,
            "documents": document_paths,
            "progress": workspace.progress.model_dump(mode="json"),
            "builder": {
                "revision": int(builder_snapshot.get("revision") or 0),
                "current_draft": builder_snapshot.get("current_draft") if isinstance(builder_snapshot.get("current_draft"), dict) else {},
                "applied_action_ids": [
                    item for item in builder_snapshot.get("applied_action_ids", [])
                    if isinstance(item, str) and item.strip()
                ] if isinstance(builder_snapshot.get("applied_action_ids"), list) else [],
            },
            "result": result or {},
        }

    @staticmethod
    def _main_agent_name(workspace: TaskWorkspace) -> str:
        return workspace.agents[0].name if workspace.agents else ""

    @staticmethod
    def _sub_agent_names(workspace: TaskWorkspace) -> list[str]:
        return [agent.name for agent in workspace.agents[1:]]
