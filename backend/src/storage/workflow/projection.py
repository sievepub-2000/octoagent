"""Workflow projection helpers used by task workspace services.

This module centralizes workflow metadata projection, archive synchronization,
and run-log append behavior while the underlying storage remains in
task_workspaces during the transition.
"""

from __future__ import annotations

from collections.abc import Callable

from src.storage.task_workspaces.contracts import TaskWorkspace
from src.storage.task_workspaces.workflow_module import TaskWorkflowModule


class WorkflowProjectionFacade:
    """Project workflow runtime state into the canonical workflow archive."""

    def __init__(self, workflow_module: TaskWorkflowModule | None = None) -> None:
        self._workflow = workflow_module or TaskWorkflowModule()

    @staticmethod
    def merge_projection_metadata(workspace: TaskWorkspace, metadata_patch: dict[str, object]) -> bool:
        merged_metadata = dict(workspace.metadata or {})
        changed = False
        for key, value in metadata_patch.items():
            if merged_metadata.get(key) == value:
                continue
            merged_metadata[key] = value
            changed = True
        if changed:
            workspace.metadata = merged_metadata
        return changed

    @staticmethod
    def projection_missing(workspace: TaskWorkspace) -> bool:
        metadata = workspace.metadata or {}
        return not metadata.get("workflow_module_version") or not metadata.get("task_dir")

    def initialize_workspace(
        self,
        workspace: TaskWorkspace,
        *,
        event_title: str | None = None,
        event_details: list[str] | None = None,
    ) -> dict[str, object]:
        return self._workflow.initialize(
            workspace,
            event_title=event_title,
            event_details=event_details,
        )

    def project_workspace(
        self,
        workspace: TaskWorkspace,
        *,
        event_title: str | None = None,
        event_details: list[str] | None = None,
    ) -> bool:
        metadata_patch = self._workflow.sync_workspace(
            workspace,
            event_title=event_title,
            event_details=list(event_details or []),
        )
        return self.merge_projection_metadata(workspace, metadata_patch)

    def sync_and_persist(
        self,
        workspace: TaskWorkspace,
        *,
        persist_workspace: Callable[[TaskWorkspace], TaskWorkspace | None],
        event_title: str | None = None,
        event_details: list[str] | None = None,
    ) -> TaskWorkspace:
        changed = self.project_workspace(
            workspace,
            event_title=event_title,
            event_details=event_details,
        )
        if changed:
            persisted = persist_workspace(workspace)
            if persisted is not None:
                return persisted
        return workspace

    def append_run_log(
        self,
        task_id: str,
        *,
        find_workspace: Callable[[str], TaskWorkspace | None],
        persist_workspace: Callable[[TaskWorkspace], TaskWorkspace | None],
        title: str,
        details: list[str] | None = None,
    ) -> None:
        workspace = find_workspace(task_id)
        if workspace is None:
            return
        self.sync_and_persist(
            workspace,
            persist_workspace=persist_workspace,
            event_title=title,
            event_details=[detail for detail in (details or []) if detail],
        )

    def delete(self, task_id: str) -> None:
        self._workflow.delete(task_id)


__all__ = ["WorkflowProjectionFacade"]
