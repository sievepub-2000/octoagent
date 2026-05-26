"""Runtime state synchronization and workspace status helpers."""

from __future__ import annotations

from src.agents.core.session import sync_workspace_session_state
from src.storage.workflow.status import (
    TERMINAL_WORKSPACE_STATUSES,
    card_status_from_agent_status,
    workspace_status_from_runtime,
)

from .contracts import TaskProgress, TaskWorkspace, utc_now


class TaskWorkspaceRuntimeState:
    """Keep persisted workspace state aligned with runtime sessions."""

    def progress(self, workspace: TaskWorkspace) -> TaskProgress:
        completed_cards = sum(1 for card in workspace.card_graph.cards if card.status == "completed")
        active_agents = sum(1 for agent in workspace.agents if agent.status in {"queued", "running", "waiting_handoff"})
        completed_agents = sum(1 for agent in workspace.agents if agent.status == "completed")
        return TaskProgress(
            completed_cards=completed_cards,
            total_cards=len(workspace.card_graph.cards),
            active_agents=active_agents,
            completed_agents=completed_agents,
            checkpoint_count=len(workspace.checkpoints),
        )

    def refresh_memory_digest(self, workspace: TaskWorkspace) -> bool:
        digest = self.workspace_memory_digest(workspace)
        if not digest:
            return False
        changed = False
        if workspace.metadata.get("project_memory_digest") != digest:
            workspace.metadata["project_memory_digest"] = digest
            changed = True
        if changed or "project_memory_updated_at" not in workspace.metadata:
            workspace.metadata["project_memory_updated_at"] = utc_now()
            changed = True
        return changed

    def sync_workspace_runtime_state(self, workspace: TaskWorkspace, query_service) -> bool:
        changed = sync_workspace_session_state(
            workspace,
            query_service=query_service,
        )
        if self.refresh_memory_digest(workspace):
            changed = True
        next_status = workspace_status_from_runtime(workspace)
        if workspace.status != next_status:
            workspace.status = next_status
            changed = True
        if self._sync_terminal_cards(workspace):
            changed = True
        if changed:
            workspace.updated_at = utc_now()
        workspace.progress = self.progress(workspace)
        return changed

    def workspace_memory_digest(self, workspace: TaskWorkspace) -> str:
        parts: list[str] = []
        goal = workspace.goal or workspace.summary or workspace.name
        if goal:
            parts.append(f"goal={goal}")
        brain_plan_summary = str(workspace.metadata.get("brain_plan_summary") or "").strip()
        if brain_plan_summary:
            parts.append(f"plan={brain_plan_summary}")
        plan_items = list(workspace.metadata.get("plan_items") or [])[:3]
        if plan_items:
            parts.append("steps=" + ", ".join(plan_items))
        last_result = str(workspace.metadata.get("last_agent_result_summary") or "").strip()
        if last_result:
            parts.append(f"last_result={last_result}")
        runtime_provider = str(workspace.metadata.get("last_runtime_provider") or "").strip()
        execution_target = str(workspace.metadata.get("last_execution_target") or "").strip()
        execution_status = str(workspace.metadata.get("last_execution_status") or "").strip()
        if execution_target or execution_status:
            if runtime_provider:
                parts.append(f"runtime={runtime_provider}@{execution_target or 'unknown'}:{execution_status or 'unknown'}")
            else:
                parts.append(f"runtime={execution_target or 'unknown'}:{execution_status or 'unknown'}")
        checkpoint_labels = [checkpoint.label for checkpoint in workspace.checkpoints[:2]]
        if checkpoint_labels:
            parts.append("checkpoints=" + ", ".join(checkpoint_labels))
        return " | ".join(part for part in parts if part)

    def _sync_terminal_cards(self, workspace: TaskWorkspace) -> bool:
        if workspace.status not in TERMINAL_WORKSPACE_STATUSES:
            return False
        changed = False
        for agent in workspace.agents:
            next_card_status = card_status_from_agent_status(agent.status)
            for card in workspace.card_graph.cards:
                if card.linked_agent_id != agent.agent_id:
                    continue
                if card.status != next_card_status:
                    card.status = next_card_status  # type: ignore[assignment]
                    changed = True
        review_status = "completed" if workspace.status == "completed" else "terminated"
        for card in workspace.card_graph.cards:
            if card.kind != "review" or card.linked_agent_id is not None:
                continue
            if card.status != review_status:
                card.status = review_status  # type: ignore[assignment]
                changed = True
        return changed
