"""Service layer for task workspaces and card graph orchestration state."""

from __future__ import annotations

import json
import logging

from src.agents.core.lifecycle import AgentLifecycleFacade
from src.agents.runtime import get_agent_runtime_manager
from src.storage.brain import BrainCoreService
from src.gateway.observability import record_exception_trace
from src.harness.orchestration import get_orchestration_service
from src.tools.plugins import get_plugin_service
from src.storage.query import QuerySession, get_query_engine_service
from src.interfaces.research import get_research_runtime_service
from src.tools.permissions import normalize_runtime_permission_mode
from src.storage.workflow.projection import WorkflowProjectionFacade

from .contracts import (
    AgentHandle,
    AgentMessage,
    CheckpointRef,
    CreateAgentMessageRequest,
    CreateCheckpointRequest,
    CreateTaskWorkspaceRequest,
    TaskWorkspace,
    TaskWorkspaceStatus,
    UpdateAgentRequest,
    UpdateTaskCardGraphRequest,
    UpdateTaskCardRequest,
    UpdateTaskWorkspaceRequest,
    make_id,
    utc_now,
)
from .defaults import TaskWorkspaceBlueprintFactory
from .planner import TaskWorkspacePlanner
from .runtime_state import TaskWorkspaceRuntimeState
from .store import TaskWorkspaceStore

logger = logging.getLogger(__name__)


class TaskWorkspaceService:
    """Facade over workspace persistence, planning, and runtime synchronization."""

    def __init__(self):
        self._store = TaskWorkspaceStore()
        self._agent_lifecycle = AgentLifecycleFacade()
        self._brain = BrainCoreService()
        self._projection = WorkflowProjectionFacade()
        self._blueprints = TaskWorkspaceBlueprintFactory()
        self._runtime_state = TaskWorkspaceRuntimeState()
        self._planner = TaskWorkspacePlanner(self._runtime_state)

    def _load(self) -> list[TaskWorkspace]:
        return self._store.list_workspaces()

    def _persist(self, workspaces: list[TaskWorkspace]) -> None:
        self._store.save_workspaces(workspaces)

    def _find(self, task_id: str) -> TaskWorkspace | None:
        return next((workspace for workspace in self._load() if workspace.task_id == task_id), None)

    def _agent_card_permission_mode(
        self,
        workspace: TaskWorkspace,
        agent: AgentHandle | None,
    ) -> str:
        if agent is not None and agent.linked_card_id is not None:
            linked_card = next(
                (card for card in workspace.card_graph.cards if card.card_id == agent.linked_card_id),
                None,
            )
            if linked_card is not None:
                return normalize_runtime_permission_mode(linked_card.permission_mode)
        mode = str(workspace.metadata.get("default_permission_mode") or "approval")
        return normalize_runtime_permission_mode(mode)

    def _update_workspace_record(
        self,
        task_id: str,
        updater,
    ) -> TaskWorkspace | None:
        workspaces = self._load()
        updated: TaskWorkspace | None = None
        for index, workspace in enumerate(workspaces):
            if workspace.task_id != task_id:
                continue
            updated = updater(workspace)
            if updated is None:
                return None
            workspaces[index] = updated
            break
        if updated is None:
            return None
        self._persist(workspaces)
        return updated

    def _resolve_agent_runtime_provider(
        self,
        *,
        requested: str | None = None,
        metadata: dict[str, object] | None = None,
        current: str | None = None,
    ) -> str:
        candidate = requested
        if candidate is None and isinstance(metadata, dict):
            metadata_value = metadata.get("agent_runtime_provider")
            if isinstance(metadata_value, str):
                candidate = metadata_value
        if candidate is None:
            candidate = current
        return get_agent_runtime_manager().resolve_provider_name(preferred=candidate)

    @staticmethod
    def _resolve_execution_strategy(requested: str | None = None) -> str:
        _ = requested
        return "fixed"

    @staticmethod
    def _parse_workflow_summary(summary: str | None) -> dict[str, object]:
        if not isinstance(summary, str):
            return {}
        raw = summary.strip()
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    @classmethod
    def _workflow_metadata_from_summary(cls, summary: str | None) -> dict[str, object]:
        payload = cls._parse_workflow_summary(summary)
        if not payload:
            return {}

        topology_candidate = str(payload.get("topology") or "").strip().lower()
        topology = topology_candidate if topology_candidate in {"chain", "branch", "swarm"} else None

        run_mode_candidate = str(payload.get("runMode") or "").strip().lower()
        run_mode = run_mode_candidate if run_mode_candidate in {"chat", "cron", "yolo"} else None

        primary_agent_candidate = payload.get("primaryAgent")
        primary_agent = primary_agent_candidate.strip() if isinstance(primary_agent_candidate, str) and primary_agent_candidate.strip() else None

        sub_agents: list[str] = []
        raw_sub_agents = payload.get("subAgents")
        if isinstance(raw_sub_agents, list):
            for item in raw_sub_agents:
                if isinstance(item, str) and item.strip():
                    sub_agents.append(item.strip())

        scheduled_at_candidate = payload.get("scheduledAt")
        scheduled_at = scheduled_at_candidate.strip() if isinstance(scheduled_at_candidate, str) and scheduled_at_candidate.strip() else None

        metadata_patch: dict[str, object] = {}
        if topology is not None:
            metadata_patch["workflow_topology"] = topology
        if run_mode is not None:
            metadata_patch["workflow_run_mode"] = run_mode
        if primary_agent is not None:
            metadata_patch["workflow_primary_agent"] = primary_agent
        if sub_agents:
            metadata_patch["workflow_sub_agents"] = sub_agents

        if run_mode == "cron":
            metadata_patch["workflow_schedule_at"] = scheduled_at
            metadata_patch["workflow_schedule_pending"] = bool(scheduled_at)
        elif run_mode is not None:
            metadata_patch["workflow_schedule_at"] = None
            metadata_patch["workflow_schedule_pending"] = False

        return metadata_patch

    def _persist_projected_workflow(
        self,
        workspace: TaskWorkspace,
        *,
        event_title: str | None = None,
        event_details: list[str] | None = None,
    ) -> TaskWorkspace:
        return self._projection.sync_and_persist(
            workspace,
            persist_workspace=lambda current: self._update_workspace_record(current.task_id, lambda _: current),
            event_title=event_title,
            event_details=list(event_details or []),
        )

    def _sync_task_projection(self, workspace: TaskWorkspace) -> TaskWorkspace:
        return self._persist_projected_workflow(workspace)

    def _sync_workflow_projection(self, workspace: TaskWorkspace) -> TaskWorkspace:
        return self._persist_projected_workflow(workspace)

    def _append_run_log(self, task_id: str, title: str, *details: str) -> None:
        self._projection.append_run_log(
            task_id,
            find_workspace=self._find,
            persist_workspace=lambda current: self._update_workspace_record(current.task_id, lambda _: current),
            title=title,
            details=[detail for detail in details if detail],
        )

    @staticmethod
    def _workflow_projection_missing(workspace: TaskWorkspace) -> bool:
        return WorkflowProjectionFacade.projection_missing(workspace)

    def compile_workspace_plan(self, task_id: str) -> TaskWorkspace | None:
        self.sync_builder_draft_topology(task_id, record_run_log=False)

        def _compile(workspace: TaskWorkspace) -> TaskWorkspace:
            return self._planner.compile_workspace_plan(
                workspace,
                brain=self._brain,
                orchestration_service=get_orchestration_service(),
                plugin_service=get_plugin_service(),
                research_runtime_service=get_research_runtime_service(),
                permission_resolver=self._agent_card_permission_mode,
            )

        workspace = self._update_workspace_record(task_id, _compile)
        if workspace is not None:
            self._sync_workflow_projection(workspace)
            self._append_run_log(task_id, "Workflow compiled", f"Status: `{workspace.status}`")
        return workspace

    def sync_builder_draft_topology(
        self,
        task_id: str,
        *,
        record_run_log: bool = True,
    ) -> TaskWorkspace | None:
        seed_messages: dict[str, list[AgentMessage]] = {}
        topology_synced = False

        def _sync(workspace: TaskWorkspace) -> TaskWorkspace:
            nonlocal seed_messages, topology_synced
            builder_state = workspace.metadata.get("brain_builder_state")
            if not isinstance(builder_state, dict):
                return workspace
            builder_draft = builder_state.get("current_draft")
            if not isinstance(builder_draft, dict):
                return workspace
            if not any(key in builder_draft for key in {"mode", "agents", "route", "branches", "collaborationStyle"}):
                return workspace

            effective_mode = self._blueprints.effective_mode_from_builder(workspace.mode, builder_draft)
            agents, seed_messages = self._blueprints.rebuild_agents(
                workspace.task_id,
                effective_mode,
                current_agents=workspace.agents,
                builder_draft=builder_draft,
                auto_research=bool(workspace.metadata.get("auto_research")),
                enabled_skills=workspace.metadata.get("enabled_skills") if isinstance(workspace.metadata.get("enabled_skills"), list) else None,
            )
            topology_synced = True
            updated = workspace.model_copy(
                update={
                    "mode": effective_mode,
                    "agents": agents,
                    "card_graph": self._blueprints.build_card_graph(
                        effective_mode,
                        goal=workspace.goal,
                        agents=agents,
                        runtime_profiles=workspace.runtime_profiles,
                        auto_research=bool(workspace.metadata.get("auto_research")),
                        enabled_skills=workspace.metadata.get("enabled_skills") if isinstance(workspace.metadata.get("enabled_skills"), list) else None,
                        topology=effective_mode,
                    ),
                    "updated_at": utc_now(),
                }
            )
            self._runtime_state.refresh_memory_digest(updated)
            updated.progress = self._runtime_state.progress(updated)
            return updated

        updated = self._update_workspace_record(task_id, _sync)
        if updated is None or not topology_synced:
            return updated

        for agent_id, messages in seed_messages.items():
            agent_name = next((agent.name for agent in updated.agents if agent.agent_id == agent_id), None)
            self._store.save_agent_messages(task_id, agent_id, messages, agent_name=agent_name)

        self._sync_task_projection(updated)
        self._sync_workflow_projection(updated)
        if record_run_log:
            self._append_run_log(
                task_id,
                "Builder topology synced",
                f"Agents: `{len(updated.agents)}`",
                f"Mode: `{updated.mode}`",
            )
        return updated

    def create_agent_handoff_session(self, task_id: str, agent_id: str) -> QuerySession | None:
        from src.agents.core import get_agent_core_service

        return get_agent_core_service().create_agent_handoff_session(task_id, agent_id, task_service=self)

    def ensure_agent_handoff_sessions(
        self,
        task_id: str,
        agent_ids: list[str] | None = None,
    ) -> TaskWorkspace | None:
        from src.agents.core import get_agent_core_service

        return get_agent_core_service().ensure_handoff_sessions(task_id, agent_ids, task_service=self)

    def create_workspace(self, request: CreateTaskWorkspaceRequest) -> TaskWorkspace:
        task_id = make_id("task")
        created_at = utc_now()

        workflow_summary_metadata = self._workflow_metadata_from_summary(request.summary)
        wizard_primary_agent = str(workflow_summary_metadata.get("workflow_primary_agent")) if isinstance(workflow_summary_metadata.get("workflow_primary_agent"), str) else None
        wizard_sub_agents = [item for item in workflow_summary_metadata.get("workflow_sub_agents", []) if isinstance(item, str)] if isinstance(workflow_summary_metadata.get("workflow_sub_agents"), list) else None
        wizard_topology = str(workflow_summary_metadata.get("workflow_topology")) if isinstance(workflow_summary_metadata.get("workflow_topology"), str) else None

        runtime_provider = self._resolve_agent_runtime_provider(requested=request.agent_runtime_provider)
        agents, seed_messages = self._blueprints.make_agents(
            task_id,
            request.mode,
            auto_research=request.auto_research,
            enabled_skills=request.enabled_skills or None,
            primary_agent=wizard_primary_agent,
            sub_agents=wizard_sub_agents,
            agent_runtime_provider=runtime_provider,
        )
        runtime_profiles = self._blueprints.selected_runtime_profiles()
        workspace = TaskWorkspace(
            task_id=task_id,
            name=request.name or f"Task {len(self._load()) + 1}",
            top_bar_label=request.name or f"Task {len(self._load()) + 1}",
            mode=request.mode,
            agent_runtime_provider=runtime_provider,
            execution_strategy=self._resolve_execution_strategy(request.execution_strategy),
            status="created",
            created_at=created_at,
            updated_at=created_at,
            goal=request.goal,
            summary=request.summary,
            deployment_interfaces=self._blueprints.default_interfaces(),
            runtime_profiles=runtime_profiles,
            agents=agents,
            card_graph=self._blueprints.build_card_graph(
                request.mode,
                goal=request.goal,
                agents=agents,
                runtime_profiles=runtime_profiles,
                auto_research=request.auto_research,
                enabled_skills=request.enabled_skills or None,
                topology=wizard_topology,
            ),
            metadata={
                "session_mode": "coordinator" if request.mode in {"branch", "group"} else "normal",
                "coordination_strategy": ("coordinator_workers" if request.mode == "branch" else ("manager_review" if request.mode == "group" else "solo")),
                "review_policy": "required" if request.mode in {"branch", "group"} else "adaptive",
                "memory_strategy": "workspace_summary_plus_checkpoints",
                "default_permission_mode": self._blueprints.default_permission_mode(request.mode),
                "supervision_rounds": 2 if request.mode in {"branch", "group"} else 1,
                "langgraph_native_runtime": True,
                "langgraph_assistant_id": "lead_agent",
                "langgraph_thread_scope": "agent" if request.mode in {"branch", "group"} else "workspace",
                "agent_runtime_provider": runtime_provider,
                "auto_research": request.auto_research,
                "enabled_skills": request.enabled_skills or [],
                "workflow_run_mode": "chat",
                "workflow_schedule_at": None,
                "workflow_schedule_pending": False,
                "expected_keywords": [kw.strip() for kw in (request.expected_keywords or []) if kw and kw.strip()],
                **({"max_turns": request.max_turns} if request.max_turns is not None else {}),
                **({"timeout_seconds": request.timeout_seconds} if request.timeout_seconds is not None else {}),
                **({"token_budget": request.token_budget} if request.token_budget is not None else {}),
                **workflow_summary_metadata,
            },
        )
        workflow_metadata = self._projection.initialize_workspace(
            workspace,
            event_title="Task created",
            event_details=[
                f"Mode: `{workspace.mode}`",
                f"Goal: {workspace.goal or workspace.name}",
            ],
        )
        workspace.metadata.update(workflow_metadata)
        self._runtime_state.refresh_memory_digest(workspace)
        workspace.progress = self._runtime_state.progress(workspace)
        workspaces = self._load()
        workspaces.append(workspace)
        self._persist(workspaces)
        for agent_id, messages in seed_messages.items():
            self._store.save_agent_messages(task_id, agent_id, messages)
        return workspace

    def delete_workspace(self, task_id: str) -> bool:
        deleted = self._store.delete_workspace(task_id)
        if not deleted:
            return False
        try:
            from src.agents.runtime import get_langgraph_workflow_contract_service

            contract = get_langgraph_workflow_contract_service().contract_for_task(task_id)
            for thread in contract.get("threads", []):
                thread_id = thread.get("thread_id") if isinstance(thread, dict) else None
                if isinstance(thread_id, str) and thread_id:
                    get_langgraph_workflow_contract_service().delete_thread_contract(thread_id)
        except Exception as exc:
            logger.warning("Failed to delete LangGraph contracts for task workspace %s", task_id, exc_info=True)
            record_exception_trace("task_workspaces.delete_workspace.contract_cleanup", exc, task_id=task_id)
        self._projection.delete(task_id)
        return True

    def list_workspaces(self) -> list[TaskWorkspace]:
        workspaces = self._load()
        changed = False
        query_service = get_query_engine_service()
        for workspace in workspaces:
            workspace_changed = self._runtime_state.sync_workspace_runtime_state(workspace, query_service)
            projection_changed = False
            if workspace_changed or self._workflow_projection_missing(workspace):
                projection_changed = self._projection.project_workspace(workspace)
            if workspace_changed or projection_changed:
                changed = True
        if changed:
            self._persist(workspaces)
        return sorted(workspaces, key=lambda item: item.updated_at, reverse=True)

    def get_workspace(self, task_id: str) -> TaskWorkspace | None:
        workspaces = self._load()
        query_service = get_query_engine_service()
        for index, workspace in enumerate(workspaces):
            if workspace.task_id != task_id:
                continue
            changed = self._runtime_state.sync_workspace_runtime_state(workspace, query_service)
            if changed or self._workflow_projection_missing(workspace):
                changed = self._projection.project_workspace(workspace) or changed
            workspaces[index] = workspace
            if changed:
                self._persist(workspaces)
            return workspace
        return None

    def update_workspace(
        self,
        task_id: str,
        request: UpdateTaskWorkspaceRequest,
    ) -> TaskWorkspace | None:
        patch = request.model_dump(exclude_none=True)

        def _update(workspace: TaskWorkspace) -> TaskWorkspace:
            requested_provider = patch.pop("agent_runtime_provider", None)
            requested_execution_strategy = patch.pop("execution_strategy", None)
            metadata_patch = patch.get("metadata") if isinstance(patch.get("metadata"), dict) else None
            updated = workspace.model_copy(update=patch)
            resolved_provider = self._resolve_agent_runtime_provider(
                requested=requested_provider,
                metadata=metadata_patch,
                current=workspace.agent_runtime_provider,
            )
            updated.agent_runtime_provider = resolved_provider
            updated.execution_strategy = self._resolve_execution_strategy(requested_execution_strategy)
            updated.metadata = dict(updated.metadata or {})
            updated.metadata["agent_runtime_provider"] = resolved_provider
            updated.metadata["execution_strategy"] = updated.execution_strategy
            updated.metadata.update(self._workflow_metadata_from_summary(updated.summary))
            updated.updated_at = utc_now()
            self._runtime_state.refresh_memory_digest(updated)
            updated.progress = self._runtime_state.progress(updated)
            return updated

        updated = self._update_workspace_record(task_id, _update)
        if updated is not None:
            self._sync_task_projection(updated)
            self._append_run_log(task_id, "Workspace updated", f"Status: `{updated.status}`")
        return updated

    def merge_workspace_metadata(self, task_id: str, **metadata) -> TaskWorkspace | None:
        workspace = self.get_workspace(task_id)
        if workspace is None:
            return None
        merged_metadata = dict(workspace.metadata or {})
        merged_metadata.update(metadata)
        return self.update_workspace(
            task_id,
            UpdateTaskWorkspaceRequest(metadata=merged_metadata),
        )

    def update_card_graph(
        self,
        task_id: str,
        request: UpdateTaskCardGraphRequest,
    ) -> TaskWorkspace | None:
        def _update(workspace: TaskWorkspace) -> TaskWorkspace:
            updated = workspace.model_copy(update={"card_graph": request.card_graph})
            updated.updated_at = utc_now()
            updated.progress = self._runtime_state.progress(updated)
            return updated

        updated = self._update_workspace_record(task_id, _update)
        if updated is not None:
            self._sync_workflow_projection(updated)
            self._append_run_log(task_id, "Card graph updated", f"Cards: `{len(updated.card_graph.cards)}`")
        return updated

    def create_checkpoint(
        self,
        task_id: str,
        request: CreateCheckpointRequest,
    ) -> TaskWorkspace | None:
        def _create(workspace: TaskWorkspace) -> TaskWorkspace:
            checkpoints = list(workspace.checkpoints)
            checkpoints.insert(
                0,
                CheckpointRef(
                    checkpoint_id=make_id("checkpoint"),
                    label=request.label or f"Checkpoint {len(checkpoints) + 1}",
                    card_id=request.card_id,
                    note=request.note,
                    task_status=workspace.status,
                    created_at=utc_now(),
                ),
            )
            updated = workspace.model_copy(update={"checkpoints": checkpoints, "updated_at": utc_now()})
            self._runtime_state.refresh_memory_digest(updated)
            updated.progress = self._runtime_state.progress(updated)
            return updated

        updated = self._update_workspace_record(task_id, _create)
        if updated is not None:
            self._sync_workflow_projection(updated)
            checkpoint = updated.checkpoints[0] if updated.checkpoints else None
            if checkpoint is not None:
                try:
                    from src.agents.runtime import get_langgraph_workflow_contract_service

                    get_langgraph_workflow_contract_service().record_checkpoint(
                        task_id=task_id,
                        thread_id=str(updated.metadata.get("last_runtime_session_id") or updated.metadata.get("langgraph_thread_id") or ""),
                        checkpoint_id=checkpoint.checkpoint_id,
                        label=checkpoint.label,
                        run_id=str(updated.metadata.get("last_runtime_step_id") or "") or None,
                        metadata={"task_status": checkpoint.task_status, "card_id": checkpoint.card_id},
                    )
                except Exception as exc:
                    logger.warning("Failed to record checkpoint %s for task %s", checkpoint.checkpoint_id, task_id, exc_info=True)
                    record_exception_trace("task_workspaces.create_checkpoint.record_checkpoint", exc, task_id=task_id, checkpoint_id=checkpoint.checkpoint_id)
            self._append_run_log(
                task_id,
                "Checkpoint created",
                f"Checkpoint: `{checkpoint.label}`" if checkpoint is not None else "",
            )
        return updated

    def set_task_status(self, task_id: str, status: TaskWorkspaceStatus) -> TaskWorkspace | None:
        workspace = self.update_workspace(task_id, UpdateTaskWorkspaceRequest(status=status))
        if workspace is not None:
            self._append_run_log(task_id, "Task status changed", f"Status: `{status}`")
        return workspace

    def list_agent_messages(self, task_id: str, agent_id: str) -> list[AgentMessage] | None:
        return self._agent_lifecycle.list_agent_messages(
            task_id,
            agent_id,
            find_workspace=self._find,
            list_messages=self._store.list_agent_messages,
        )

    def append_agent_message(
        self,
        task_id: str,
        agent_id: str,
        request: CreateAgentMessageRequest,
        *,
        assistant_content: str | None = None,
    ) -> list[AgentMessage] | None:
        return self._agent_lifecycle.append_agent_message(
            task_id,
            agent_id,
            request,
            assistant_content=assistant_content,
            load_workspaces=self._load,
            persist_workspaces=self._persist,
            list_messages=self._store.list_agent_messages,
            save_messages=lambda task_id, agent_id, messages, agent_name: self._store.save_agent_messages(
                task_id,
                agent_id,
                messages,
                agent_name=agent_name,
            ),
            progress_for_workspace=self._runtime_state.progress,
            append_run_log=self._append_run_log,
        )

    def set_agent_status(
        self,
        task_id: str,
        agent_id: str,
        status: str,
    ) -> TaskWorkspace | None:
        workspace = self._agent_lifecycle.set_agent_status(
            task_id,
            agent_id,
            status,
            update_workspace_record=self._update_workspace_record,
            progress_for_workspace=self._runtime_state.progress,
        )
        if workspace is not None:
            self._append_run_log(task_id, "Agent status changed", f"Agent ID: `{agent_id}`", f"Status: `{status}`")
        return workspace

    def update_agent(
        self,
        task_id: str,
        agent_id: str,
        request: UpdateAgentRequest,
    ) -> TaskWorkspace | None:
        updated = self._agent_lifecycle.update_agent(
            task_id,
            agent_id,
            request,
            update_workspace_record=self._update_workspace_record,
            progress_for_workspace=self._runtime_state.progress,
        )
        if updated is not None:
            self._sync_task_projection(updated)
            self._sync_workflow_projection(updated)
        return updated

    def update_card(
        self,
        task_id: str,
        card_id: str,
        request: UpdateTaskCardRequest,
    ) -> TaskWorkspace | None:
        def _update(workspace: TaskWorkspace) -> TaskWorkspace | None:
            card = next((item for item in workspace.card_graph.cards if item.card_id == card_id), None)
            if card is None:
                return None
            if request.title is not None:
                card.title = request.title
            if request.description is not None:
                card.description = request.description
            if request.config is not None:
                card.config.update(request.config)
            if request.tags is not None:
                card.tags = request.tags
            if request.linked_agent_id is not None:
                card.linked_agent_id = request.linked_agent_id
            workspace.updated_at = utc_now()
            workspace.progress = self._runtime_state.progress(workspace)
            return workspace

        updated = self._update_workspace_record(task_id, _update)
        if updated is not None:
            self._sync_workflow_projection(updated)
        return updated


_service = TaskWorkspaceService()


def get_task_workspace_service() -> TaskWorkspaceService:
    return _service
