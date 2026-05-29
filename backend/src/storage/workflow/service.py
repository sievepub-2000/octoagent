"""Gateway-facing workflow application service.

This facade keeps external callers decoupled from the underlying
``task_workspaces`` implementation while WorkflowCore is extracted in slices.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agents.core.session import build_agent_runtime_summary, build_handoff_summary
from src.runtime.config.extensions_config import get_extensions_config
from src.storage.query import get_query_engine_service
from src.storage.task_workspaces import (
    TaskWorkspaceExecutionController,
    TaskWorkspaceMessageExecutor,
    TaskWorkspaceService,
    get_task_workspace_execution_controller,
    get_task_workspace_message_executor,
    get_task_workspace_service,
)
from src.storage.task_workspaces.workflow_module import TaskWorkflowModule
from src.storage.workflow.builder_transactions import (
    BuilderApplyResponse,
    BuilderHistoryResponse,
    BuilderPreviewResponse,
    BuilderTransactionService,
)
from src.storage.workflow.observation import parse_run_log_timeline
from src.storage.workflow.public_runtime_contracts import (
    PublicBindings,
)
from src.storage.workflow.public_runtime_contracts import (
    project_public_bindings as _project_public_bindings,
)
from src.storage.workflow.runtime_contracts import TaskStudioRuntimeEventsResponse, TaskStudioRuntimeResponse
from src.storage.workflow.status import workflow_stage_for_status
from src.tools.system_execution import get_system_execution_service


class WorkflowCoreService:
    """Stable workflow boundary for gateway, CLI, and future client adapters."""

    def __init__(self, delegate: TaskWorkspaceService):
        self._delegate = delegate
        self._workflow_module = TaskWorkflowModule()
        self._builder_transactions = BuilderTransactionService()

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def read_run_log(self, task_id: str) -> str | None:
        return self._workflow_module._files.read_run_log(task_id)

    def read_result(self, task_id: str) -> str | None:
        return self._workflow_module._files.read_result(task_id)

    def read_result_payload(self, task_id: str) -> dict[str, object]:
        return self._workflow_module._files.read_result_payload(task_id)

    def list_artifacts(self, task_id: str) -> list[dict[str, str]]:
        return self._workflow_module._files.sync_task_attachments(task_id)

    def resolve_artifact_path(self, task_id: str, relative_path: str) -> Path | None:
        return self._workflow_module._files.resolve_artifact_path(task_id, relative_path)

    def get_studio_runtime_contract(self, task_id: str) -> dict[str, object] | None:
        workspace = self.get_workspace(task_id)
        if workspace is None:
            return None

        metadata = workspace.metadata or {}
        query_sessions = [session for session in get_query_engine_service().list_sessions() if session.task_id == task_id]
        query_sessions.sort(key=lambda item: item.updated_at, reverse=True)
        latest_session = query_sessions[0] if query_sessions else None
        artifacts = self.list_artifacts(task_id)
        run_log = self.read_run_log(task_id) or "# Workflow Run Log\n\n## Final Results\n\n_Results pending._\n"
        timeline = parse_run_log_timeline(run_log)
        terminal_sessions = get_system_execution_service().list_sessions(
            related_task_id=task_id,
            limit=12,
        )
        card_counts = _card_status_counts(workspace)

        # Delegate to agent_core for centralized aggregation
        agent_items = build_agent_runtime_summary(workspace, query_sessions)
        handoffs = build_handoff_summary(workspace, query_sessions)

        active_query_sessions = [session for session in query_sessions if session.status in {"ready", "running", "paused"}]

        extensions = get_extensions_config()
        configured_skills = metadata.get("enabled_skills") if isinstance(metadata.get("enabled_skills"), list) else []
        active_plugin_ids = metadata.get("active_plugin_ids") if isinstance(metadata.get("active_plugin_ids"), list) else []
        channel_bindings = _build_studio_channel_bindings(workspace)
        bindings = {
            "channels": [
                {
                    "binding_id": f"channel:{binding['kind']}:{binding['label']}:{binding['source']}",
                    "kind": binding["kind"],
                    "label": binding["label"],
                    "enabled": binding["enabled"],
                    "status": binding["status"],
                    "source": binding["source"],
                }
                for binding in channel_bindings
            ],
            "mcp_servers": [
                {
                    "binding_id": f"mcp:{server_name}",
                    "kind": "mcp",
                    "label": server_name,
                    "enabled": server.enabled,
                    "status": "enabled" if server.enabled else "disabled",
                    "source": "extensions_config",
                }
                for server_name, server in sorted(extensions.mcp_servers.items(), key=lambda item: item[0])
            ],
            "skills": [
                {
                    "binding_id": f"skill:{skill_name}",
                    "kind": "skill",
                    "label": skill_name,
                    "enabled": True,
                    "status": "enabled",
                    "source": "workspace_metadata",
                }
                for skill_name in configured_skills
                if isinstance(skill_name, str) and skill_name.strip()
            ],
            "plugins": [
                {
                    "binding_id": f"plugin:{plugin_id}",
                    "kind": "plugin",
                    "label": plugin_id,
                    "enabled": True,
                    "status": "active",
                    "source": "workspace_metadata",
                }
                for plugin_id in active_plugin_ids
                if isinstance(plugin_id, str) and plugin_id.strip()
            ],
        }

        memory_guard_state = "unknown"
        if latest_session is not None:
            pressure = latest_session.memory_profile.context_pressure
            memory_guard_state = "tight" if pressure == "high" else "watch" if pressure == "medium" else "ok"

        latest_checkpoint = workspace.checkpoints[-1] if workspace.checkpoints else None
        try:
            from src.agents.runtime import get_langgraph_workflow_contract_service

            langgraph_contract = get_langgraph_workflow_contract_service().contract_for_task(task_id)
        except Exception:
            langgraph_contract = {"task_id": task_id, "threads": [], "summary": {}}
        timeline_items = _build_timeline_items(workspace, timeline, terminal_sessions)
        active_handoff_count = len([handoff for handoff in handoffs if handoff.get("status") in {"ready", "running", "paused"}])
        enabled_binding_count = sum(1 for binding_group in bindings.values() for binding in binding_group if bool(binding.get("enabled")))
        raw_contract = {
            "task_id": workspace.task_id,
            "name": workspace.name,
            "mode": workspace.mode,
            "status": workspace.status,
            "goal": workspace.goal,
            "updated_at": workspace.updated_at,
            "progress": workspace.progress,
            "workflow_summary": {
                "graph_version": str(metadata.get("workflow_module_version") or metadata.get("compiled_graph_id") or "task-workflow-v2"),
                "cards_total": len(workspace.card_graph.cards),
                "active_cards": len([card for card in workspace.card_graph.cards if card.status in {"running", "paused", "blocked"}]),
                "completed_cards": card_counts["completed"],
                "blocked_cards": card_counts["blocked"],
                "queued_cards": card_counts["configured"] + card_counts["idle"],
                "review_policy": str(metadata.get("review_policy") or "adaptive"),
            },
            "agents": agent_items,
            "timeline": timeline_items,
            "handoffs": handoffs,
            "artifacts": [
                {
                    "name": artifact["name"],
                    "path": artifact["path"],
                    "download_url": f"/api/task-workspaces/{task_id}/artifacts/{artifact['path']}?download=true",
                }
                for artifact in artifacts
            ],
            "bindings": bindings,
            "channel_bindings": channel_bindings,
            "checkpoints": workspace.checkpoints,
            "checkpoints_summary": {
                "total": len(workspace.checkpoints),
                "latest": latest_checkpoint.checkpoint_id if latest_checkpoint is not None else None,
                "ready_for_review": workspace.status in {"waiting_review", "completed"} or bool(metadata.get("review_completed")),
            },
            "readiness": {
                "can_run": workspace.status in {"created", "planned", "paused", "waiting_review"},
                "can_resume": workspace.status in {"paused", "waiting_review"},
                "requires_review": workspace.status == "waiting_review" or bool(metadata.get("review_required")),
                "blocked_cards": card_counts["blocked"],
                "queued_cards": card_counts["configured"] + card_counts["idle"],
                "completed_cards": card_counts["completed"],
                "active_handoffs": active_handoff_count,
                "enabled_bindings": enabled_binding_count,
                "artifact_count": len(artifacts),
            },
            "runtime_summary": {
                "project_memory_digest": _metadata_string(metadata, "project_memory_digest"),
                "project_memory_updated_at": _metadata_string(metadata, "project_memory_updated_at"),
                "latest_query_session_id": latest_session.session_id if latest_session is not None else next((str(item.get("query_session_id")) for item in agent_items if item.get("query_session_id")), None),
                "latest_runtime_session_id": next((str(item.get("runtime_session_id")) for item in agent_items if item.get("runtime_session_id")), None),
                "active_query_sessions": len(active_query_sessions) if active_query_sessions else sum(1 for item in agent_items if item.get("query_session_id")),
                "active_runtime_sessions": len({str(item.get("runtime_session_id")) for item in agent_items if isinstance(item.get("runtime_session_id"), str) and str(item.get("runtime_session_id")).strip()}),
                "memory_guard_state": memory_guard_state,
                "current_phase": workflow_stage_for_status(workspace.status),
                "last_runtime_sync_at": _metadata_string(metadata, "last_runtime_sync_at") or workspace.updated_at,
                "langgraph_graph_id": _metadata_string(metadata, "langgraph_graph_id") or _metadata_string(metadata, "compiled_graph_id"),
                "last_langgraph_assistant_id": _metadata_string(metadata, "langgraph_assistant_id") or next((str(item.get("langgraph_assistant_id")) for item in agent_items if item.get("langgraph_assistant_id")), None),
                "langgraph_thread_scope": _metadata_string(metadata, "langgraph_thread_scope"),
                "langgraph_native_runtime": bool(metadata.get("langgraph_native_runtime", False)),
                "last_runtime_provider": _metadata_string(metadata, "last_runtime_provider") or next((str(item.get("last_runtime_provider")) for item in agent_items if item.get("last_runtime_provider")), None),
                "last_execution_target": _metadata_string(metadata, "last_execution_target") or next((str(item.get("last_execution_target")) for item in agent_items if item.get("last_execution_target")), None),
                "last_execution_status": _metadata_string(metadata, "last_execution_status") or next((str(item.get("last_execution_status")) for item in agent_items if item.get("last_execution_status")), None),
                "last_agent_result_summary": _metadata_string(metadata, "last_agent_result_summary") or next((str(item.get("last_result_summary")) for item in agent_items if item.get("last_result_summary")), None),
                "langgraph_contract": langgraph_contract.get("summary", {}),
            },
            "run_log": run_log,
        }
        return TaskStudioRuntimeResponse.model_validate(raw_contract).model_dump(mode="json")

    def list_studio_runtime_events(
        self,
        task_id: str,
        *,
        cursor: int = 0,
        limit: int = 20,
    ) -> dict[str, object] | None:
        workspace = self.get_workspace(task_id)
        if workspace is None:
            return None

        run_log = self.read_run_log(task_id) or "# Workflow Run Log\n\n## Final Results\n\n_Results pending._\n"
        timeline = parse_run_log_timeline(run_log)
        terminal_sessions = get_system_execution_service().list_sessions(
            related_task_id=task_id,
            limit=max(limit, 12),
        )
        events = _build_timeline_items(workspace, timeline, terminal_sessions)
        safe_cursor = max(cursor, 0)
        safe_limit = max(min(limit, 100), 1)
        page = events[safe_cursor : safe_cursor + safe_limit]
        next_cursor = safe_cursor + safe_limit if safe_cursor + safe_limit < len(events) else None
        return TaskStudioRuntimeEventsResponse.model_validate(
            {
                "task_id": task_id,
                "cursor": safe_cursor,
                "next_cursor": next_cursor,
                "events": page,
            }
        ).model_dump(mode="json")

    # ------------------------------------------------------------------
    # Public runtime projection (Slice E)
    # ------------------------------------------------------------------


    def get_public_bindings(self, task_id: str) -> dict[str, object] | None:
        """Return the current workflow bindings for external consumption."""
        contract = self.get_studio_runtime_contract(task_id)
        if contract is None:
            return None
        bindings = contract.get("bindings") or {}
        return PublicBindings.model_validate(_project_public_bindings(bindings)).model_dump(mode="json")

    def update_public_bindings(
        self,
        task_id: str,
        *,
        channels: list[str] | None = None,
        mcp_servers: list[str] | None = None,
        skills: list[str] | None = None,
        plugins: list[str] | None = None,
    ) -> dict[str, object] | None:
        """Update workflow-bound activation metadata.

        Only updates fields that are provided (non-None).
        Returns the updated binding snapshot.
        """
        workspace = self.get_workspace(task_id)
        if workspace is None:
            return None
        metadata = dict(workspace.metadata or {})

        if channels is not None:
            metadata["channel_bindings"] = [{"kind": ch, "label": ch, "enabled": True, "status": "enabled"} for ch in channels if isinstance(ch, str) and ch.strip()]
        if skills is not None:
            metadata["enabled_skills"] = [s for s in skills if isinstance(s, str) and s.strip()]
        if plugins is not None:
            metadata["active_plugin_ids"] = [p for p in plugins if isinstance(p, str) and p.strip()]
        # Note: mcp_servers are global (extensions_config), not per-workspace.
        # We store the user's intent so the binding view reflects it.
        if mcp_servers is not None:
            metadata["bound_mcp_servers"] = [m for m in mcp_servers if isinstance(m, str) and m.strip()]

        if self._delegate.merge_workspace_metadata(task_id, **metadata) is None:
            return None
        return self.get_public_bindings(task_id)


    # ------------------------------------------------------------------
    # Builder transaction delegation (Slice D)
    # ------------------------------------------------------------------

    def get_builder_preview(self, task_id: str) -> BuilderPreviewResponse | None:
        workspace = self.get_workspace(task_id)
        if workspace is None:
            return None
        return self._builder_transactions.generate_preview(workspace)

    def apply_builder_action(
        self,
        task_id: str,
        action_id: str,
    ) -> BuilderApplyResponse | None:
        workspace = self.get_workspace(task_id)
        if workspace is None:
            return None
        preview = self._builder_transactions.generate_preview(workspace)
        response, new_state = self._builder_transactions.apply_action(workspace, preview, action_id)
        self._persist_builder_state(task_id, new_state)
        return response

    def apply_builder_action_batch(
        self,
        task_id: str,
        *,
        action_ids: list[str] | None = None,
        use_apply_all_patch: bool = False,
    ) -> BuilderApplyResponse | None:
        workspace = self.get_workspace(task_id)
        if workspace is None:
            return None
        preview = self._builder_transactions.generate_preview(workspace)
        response, new_state = self._builder_transactions.apply_batch(
            workspace,
            preview,
            action_ids=action_ids,
            use_apply_all_patch=use_apply_all_patch,
        )
        self._persist_builder_state(task_id, new_state)
        return response

    def get_builder_history(self, task_id: str) -> BuilderHistoryResponse | None:
        workspace = self.get_workspace(task_id)
        if workspace is None:
            return None
        return self._builder_transactions.get_history(workspace)

    def _persist_builder_state(self, task_id: str, state: dict[str, Any]) -> None:
        workspace = self.get_workspace(task_id)
        if workspace is None:
            return
        merged_metadata = dict(workspace.metadata or {})
        merged_metadata["brain_builder_state"] = state
        workspace.metadata = merged_metadata
        self._delegate.save_workspace(workspace)
        self.sync_builder_draft_topology(task_id)


def _metadata_string(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _card_status_counts(workspace) -> dict[str, int]:
    counts = {
        "idle": 0,
        "configured": 0,
        "running": 0,
        "paused": 0,
        "blocked": 0,
        "completed": 0,
        "terminated": 0,
    }
    for card in workspace.card_graph.cards:
        if card.status in counts:
            counts[card.status] += 1
    return counts


def _build_timeline_items(workspace, timeline: list[dict[str, object]], terminal_sessions) -> list[dict[str, object]]:
    timeline_items = [
        {
            "event_id": f"timeline-{index + 1}",
            "kind": "run_log_event",
            "created_at": str(event.get("created_at") or workspace.updated_at),
            "title": str(event.get("title") or "Run log event"),
            "details": [str(item) for item in event.get("details", []) if str(item).strip()],
            "summary": str(event.get("title") or "Run log event"),
            "source": "run_log",
            "agent_id": event.get("agent_id") if isinstance(event.get("agent_id"), str) else None,
            "card_id": event.get("card_id") if isinstance(event.get("card_id"), str) else None,
            "session_id": event.get("session_id") if isinstance(event.get("session_id"), str) else None,
        }
        for index, event in enumerate(timeline)
    ]
    for session in terminal_sessions:
        session_target = "system CLI" if session.target == "system_cli" else "workspace CLI"
        session_command = session.last_command or (session.requested_commands[0] if session.requested_commands else "bounded command")
        session_details = [f"Scope: {session_target}", f"Status: {session.status}"]
        if session.last_exit_code is not None:
            session_details.append(f"Exit code: {session.last_exit_code}")
        if session.related_task_name:
            session_details.append(f"Task: {session.related_task_name}")
        timeline_items.append(
            {
                "event_id": f"terminal-{session.session_id}",
                "kind": "terminal_session",
                "created_at": str(session.updated_at or workspace.updated_at),
                "title": f"{session_target} executed {session_command}",
                "details": session_details,
                "summary": f"{session_target} {session.status}",
                "source": "system_execution",
                "session_id": session.session_id,
            }
        )
    timeline_items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return timeline_items


def _build_studio_channel_bindings(workspace) -> list[dict[str, object]]:
    bindings = [
        {
            "kind": deployment.kind,
            "label": deployment.label,
            "enabled": deployment.enabled,
            "status": "enabled" if deployment.enabled else "disabled",
            "source": "deployment_interface",
        }
        for deployment in workspace.deployment_interfaces
    ]
    metadata = workspace.metadata or {}
    configured_channels = metadata.get("channel_bindings")
    if isinstance(configured_channels, list):
        for item in configured_channels:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind")
            label = item.get("label")
            if not isinstance(kind, str) or not isinstance(label, str):
                continue
            bindings.append(
                {
                    "kind": kind,
                    "label": label,
                    "enabled": bool(item.get("enabled", True)),
                    "status": str(item.get("status") or ("enabled" if item.get("enabled", True) else "disabled")),
                    "source": "workspace_metadata",
                }
            )
    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for binding in bindings:
        key = (str(binding["kind"]), str(binding["label"]), str(binding["source"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(binding)
    return deduped


_service = WorkflowCoreService(get_task_workspace_service())


def get_workflow_core_service() -> WorkflowCoreService:
    return _service


def get_workflow_execution_controller() -> TaskWorkspaceExecutionController:
    return get_task_workspace_execution_controller()


def get_workflow_message_executor() -> TaskWorkspaceMessageExecutor:
    return get_task_workspace_message_executor()


__all__ = [
    "TaskWorkflowModule",
    "WorkflowCoreService",
    "get_workflow_core_service",
    "get_workflow_execution_controller",
    "get_workflow_message_executor",
]
