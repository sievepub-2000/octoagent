"""Service layer for query-engine sessions."""

from __future__ import annotations

import os

from src.agents.memory import get_memory_data
from src.interfaces.research import get_research_runtime_service
from src.runtime.config.extensions_config import ExtensionsConfig
from src.runtime.config.ml_intern_defaults import build_ml_intern_runtime_context
from src.runtime.config.paths import get_paths
from src.tools.permissions import normalize_runtime_permission_mode
from src.tools.sandbox.browser import get_browser_runtime_service
from src.tools.system_execution import get_system_execution_service

from .contracts import (
    QueryClientCommand,
    QueryEngineCapability,
    QueryOperationPlanRequest,
    QueryOperationPlanResponse,
    QueryRuntimeEvent,
    QuerySession,
    QuerySessionCompactRequest,
    QuerySessionGovernance,
    QuerySessionRefreshRequest,
    QuerySessionSummary,
    QueryTurn,
    QueryTurnExecutionRequest,
    QueryTurnRecordRequest,
)
from .execution import QueryTurnExecutor
from .governance import build_session_governance
from .profile import QuerySessionProfileAssembler


def _make_id(prefix: str, seed: str) -> str:
    return f"{prefix}-{seed}"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return default


class QueryEngineService:
    """Facade over query session storage, profile assembly, and turn execution."""

    def __init__(self):
        self._sessions: dict[str, QuerySession] = {}
        self._max_active_turns = _env_int("OCTO_QUERY_MAX_ACTIVE_TURNS", 8)
        self._max_runtime_events = _env_int("OCTO_QUERY_MAX_RUNTIME_EVENTS", 120)
        self._max_summaries = _env_int("OCTO_QUERY_MAX_SUMMARIES", 20)
        self._profiles = QuerySessionProfileAssembler(
            _make_id,
            self._append_event,
            get_memory_data_fn=lambda: get_memory_data(),
            extensions_config_cls=ExtensionsConfig,
            get_paths_fn=get_paths,
        )
        self._executor = QueryTurnExecutor(
            _make_id,
            get_browser_runtime_service_fn=lambda: get_browser_runtime_service(),
            get_research_runtime_service_fn=lambda: get_research_runtime_service(),
            get_system_execution_service_fn=lambda: get_system_execution_service(),
        )

    def get_capability(self) -> QueryEngineCapability:
        return QueryEngineCapability()

    def plan_operation(self, request: QueryOperationPlanRequest) -> QueryOperationPlanResponse:
        client_command = self._executor.resolve_client_command(
            request.user_message,
            permission_mode=request.permission_mode,
        )
        governance = build_session_governance(
            current_goal=request.current_goal,
            user_message=request.user_message,
            memory_profile=None,
            active_operation=client_command,
            continuation_source=request.continuation_source,
            archived_turn_count=request.archived_turn_count,
        )
        return QueryOperationPlanResponse(
            normalized_message=request.user_message.strip(),
            command=client_command,
            governance=governance,
        )

    def list_sessions(self) -> list[QuerySession]:
        return sorted(self._sessions.values(), key=lambda item: item.updated_at, reverse=True)

    def get_session(self, session_id: str) -> QuerySession | None:
        return self._sessions.get(session_id)

    def recover_session(
        self,
        session_id: str,
        *,
        created_at: str,
        reason: str = "stale_session_recovery",
    ) -> QuerySession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.status == "running":
            session.status = "paused"
        session.metadata["last_recovery_reason"] = reason
        session.metadata["last_recovered_at"] = created_at
        self._append_event(
            session,
            kind="continuation_applied",
            detail=f"Stale session recovery applied: {reason}.",
            created_at=created_at,
        )
        self._enforce_session_budget(session, created_at=created_at)
        return session

    def recover_stale_sessions(self, *, created_at: str, reason: str = "operator_recovery") -> dict[str, object]:
        recovered: list[str] = []
        for session in self._sessions.values():
            if session.status != "running":
                continue
            session.status = "paused"
            session.metadata["last_recovered_at"] = created_at
            session.metadata["last_recovery_reason"] = reason
            self._append_event(
                session,
                kind="stale_thread_recovered",
                detail=f"Recovered stale running session: {reason}.",
                created_at=created_at,
            )
            self._enforce_session_budget(session, created_at=created_at)
            recovered.append(session.session_id)
        return {
            "recovered_count": len(recovered),
            "session_ids": recovered,
            "snapshot": self.maintenance_snapshot(),
        }

    def evaluate_summary_quality(self, session_id: str, *, created_at: str) -> dict[str, object] | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        evaluations = []
        for summary in session.summaries:
            score, notes = self._score_summary(summary.content, summary.open_items)
            summary.quality_score = score
            summary.quality_notes = notes
            if score < 0.6:
                session.metadata["summary_degradation_detected"] = True
                session.metadata["summary_degradation_summary_id"] = summary.summary_id
            evaluations.append(
                {
                    "summary_id": summary.summary_id,
                    "quality_score": score,
                    "quality_notes": notes,
                    "open_item_count": len(summary.open_items),
                }
            )
        session.metadata["last_summary_quality_evaluated_at"] = created_at
        self._append_event(
            session,
            kind="summary_quality_evaluated",
            detail=f"Evaluated {len(evaluations)} summary item(s).",
            created_at=created_at,
        )
        return {
            "session_id": session_id,
            "summary_count": len(evaluations),
            "evaluations": evaluations,
        }

    def build_replay_context(self, session_id: str, *, created_at: str) -> dict[str, object] | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        latest_summary = session.summaries[-1] if session.summaries else None
        payload = {
            "session_id": session.session_id,
            "task_id": session.task_id,
            "agent_id": session.agent_id,
            "tenant_id": str(session.metadata.get("tenant_id") or "default"),
            "current_goal": session.current_goal,
            "status": session.status,
            "archived_turn_count": int(session.metadata.get("archived_turn_count", 0)),
            "latest_summary": latest_summary.model_dump(mode="json") if latest_summary else None,
            "active_turns": [turn.model_dump(mode="json") for turn in session.turns],
            "continuation": session.governance.model_dump(mode="json"),
            "assembled_system_prompt": session.assembled_system_prompt,
            "summary_degradation_detected": bool(session.metadata.get("summary_degradation_detected")),
        }
        session.metadata["last_replay_context_built_at"] = created_at
        self._append_event(
            session,
            kind="replay_context_built",
            detail="Built replay context for cross-process/session continuation.",
            created_at=created_at,
        )
        return payload

    def maintenance_snapshot(self) -> dict[str, object]:
        session_count = len(self._sessions)
        turn_count = sum(len(session.turns) for session in self._sessions.values())
        summary_count = sum(len(session.summaries) for session in self._sessions.values())
        runtime_event_count = sum(len(session.runtime_events) for session in self._sessions.values())
        pressure = {
            "low": 0,
            "medium": 0,
            "high": 0,
        }
        for session in self._sessions.values():
            pressure[session.memory_profile.context_pressure] = pressure.get(session.memory_profile.context_pressure, 0) + 1
        return {
            "session_count": session_count,
            "turn_count": turn_count,
            "summary_count": summary_count,
            "runtime_event_count": runtime_event_count,
            "context_pressure": pressure,
            "budgets": {
                "max_active_turns": self._max_active_turns,
                "max_runtime_events": self._max_runtime_events,
                "max_summaries": self._max_summaries,
            },
        }

    def run_maintenance(self, *, created_at: str) -> dict[str, object]:
        compacted_sessions = 0
        trimmed_events = 0
        trimmed_summaries = 0
        recovered_sessions = 0
        quality_evaluations = 0
        for session in list(self._sessions.values()):
            if session.status == "running":
                session.status = "paused"
                session.metadata["last_recovered_at"] = created_at
                session.metadata["last_recovery_reason"] = "maintenance_paused_stale_running_session"
                recovered_sessions += 1
            before_events = len(session.runtime_events)
            before_summaries = len(session.summaries)
            before_turns = len(session.turns)
            self._enforce_session_budget(session, created_at=created_at)
            if len(session.turns) < before_turns:
                compacted_sessions += 1
            trimmed_events += max(0, before_events - len(session.runtime_events))
            trimmed_summaries += max(0, before_summaries - len(session.summaries))
            for summary in session.summaries:
                summary.quality_score, summary.quality_notes = self._score_summary(
                    summary.content,
                    summary.open_items,
                )
                quality_evaluations += 1
        return {
            "compacted_sessions": compacted_sessions,
            "trimmed_events": trimmed_events,
            "trimmed_summaries": trimmed_summaries,
            "recovered_sessions": recovered_sessions,
            "summary_quality_evaluations": quality_evaluations,
            "snapshot": self.maintenance_snapshot(),
        }

    def latest_session_for_agent(self, task_id: str, agent_id: str) -> QuerySession | None:
        candidates = [session for session in self._sessions.values() if session.task_id == task_id and session.agent_id == agent_id]
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item.updated_at, reverse=True)[0]

    def create_workspace_session(
        self,
        workspace,
        agent,
        prompt_stack,
        *,
        created_at: str,
    ) -> QuerySession:
        previous_session = self.latest_session_for_agent(workspace.task_id, agent.agent_id)
        previous_summary = previous_session.summaries[-1] if previous_session and previous_session.summaries else None
        next_index = len([session for session in self._sessions.values() if session.task_id == workspace.task_id and session.agent_id == agent.agent_id]) + 1
        session_id = _make_id("query-session", f"{workspace.task_id}-{agent.agent_id}-{next_index}")
        session = QuerySession(
            session_id=session_id,
            task_id=workspace.task_id,
            agent_id=agent.agent_id,
            status="ready",
            current_goal=workspace.goal or workspace.summary or workspace.name,
            prompt_stack_profile_id=prompt_stack.profile_id,
            turns=[
                QueryTurn(
                    turn_id=_make_id("turn", f"{workspace.task_id}-{agent.agent_id}-1"),
                    status="planned",
                    user_message=workspace.goal or workspace.summary or workspace.name,
                    assistant_summary="Initial handoff turn prepared from task workspace state.",
                    created_at=created_at,
                )
            ],
            metadata={
                "workspace_mode": workspace.mode,
                "tenant_id": str((workspace.metadata or {}).get("tenant_id") or "default"),
                "tenant_tier": str((workspace.metadata or {}).get("tenant_tier") or "free"),
                "tenant_policy": dict((workspace.metadata or {}).get("tenant_policy") or {}),
                "agent_role": agent.role,
                "permission_mode": self._agent_permission_mode(workspace, agent),
                **build_ml_intern_runtime_context(
                    permission_mode=self._agent_permission_mode(workspace, agent),
                    workflow_run_mode=workspace.metadata.get("workflow_run_mode"),
                ),
                "compiled_graph_id": workspace.metadata.get("compiled_graph_id"),
                "research_experiment_id": workspace.metadata.get("research_experiment_id"),
                "active_plugin_ids": list(workspace.metadata.get("active_plugin_ids") or []),
                "previous_session_id": previous_session.session_id if previous_session is not None else None,
                "previous_summary_id": previous_summary.summary_id if previous_summary is not None else None,
            },
            created_at=created_at,
            updated_at=created_at,
        )
        self._profiles.refresh_session_profile(
            session,
            workspace,
            agent,
            prompt_stack,
            created_at=created_at,
            reason="session_created",
            previous_summary=previous_summary,
            permission_mode_resolver=self._agent_permission_mode,
        )
        self._append_event(
            session,
            kind="session_created",
            detail="Workspace handoff session created from orchestration prompt stack.",
            created_at=created_at,
        )
        self._profiles.update_memory_profile(session)
        session.governance = self._build_governance(
            session,
            user_message=session.current_goal,
            client_command=self._executor.resolve_client_command(
                session.current_goal,
                permission_mode=normalize_runtime_permission_mode(str(session.metadata.get("permission_mode") or "approval")),
            ),
        )
        self._sessions[session_id] = session
        return session

    def refresh_session_profile(
        self,
        session_id: str,
        workspace,
        agent,
        prompt_stack,
        request: QuerySessionRefreshRequest,
        *,
        created_at: str,
    ) -> QuerySession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        previous_summary = session.summaries[-1] if session.summaries else None
        self._profiles.refresh_session_profile(
            session,
            workspace,
            agent,
            prompt_stack,
            created_at=created_at,
            reason=request.reason,
            previous_summary=previous_summary,
            permission_mode_resolver=self._agent_permission_mode,
        )
        session.governance = self._build_governance(
            session,
            user_message=session.current_goal,
            client_command=self._executor.resolve_client_command(
                session.current_goal,
                permission_mode=normalize_runtime_permission_mode(str(session.metadata.get("permission_mode") or "approval")),
            ),
        )
        return session

    def execute_turn(
        self,
        session_id: str,
        request: QueryTurnExecutionRequest,
        *,
        created_at: str,
    ) -> QuerySession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if request.force_profile_refresh:
            session.metadata["last_forced_profile_refresh_at"] = created_at
            self._append_event(
                session,
                kind="context_snapshot_built",
                detail="Forced profile refresh requested before turn execution.",
                created_at=created_at,
            )
            self._profiles.update_memory_profile(session)
        client_command = request.client_command or self._executor.resolve_client_command(
            request.user_message,
            permission_mode=normalize_runtime_permission_mode(str(session.metadata.get("permission_mode") or "approval")),
        )
        target = self._executor.select_execution_target(request.user_message, client_command)
        allow_side_effects = request.allow_side_effects or normalize_runtime_permission_mode(str(session.metadata.get("permission_mode") or "approval")) == "system"
        approval_required = self._executor.approval_required(session, target, request.user_message)
        memory_action = "refreshed" if request.force_profile_refresh else "none"
        session.governance = self._build_governance(session, user_message=request.user_message, client_command=client_command)
        self._append_event(
            session,
            kind="client_command_planned",
            detail=(f"Client operation '{client_command.operation_id}' mapped to intent '{client_command.intent}' and target '{client_command.execution_target}'."),
            created_at=created_at,
        )
        if session.governance.continuation_mode != "fresh":
            self._append_event(
                session,
                kind="continuation_applied",
                detail=session.governance.continuity_summary,
                created_at=created_at,
            )
        if session.governance.goal_drift.status != "aligned":
            self._append_event(
                session,
                kind="goal_drift_detected",
                detail=session.governance.goal_drift.reason,
                created_at=created_at,
            )
        if approval_required and not allow_side_effects:
            assistant_summary = f"Execution target '{target}' requires approval. Turn recorded without side effects; enable approved execution to continue."
            execution_status = "blocked"
            tool_call_count = 0
            runtime_session_id = None
            runtime_step_id = None
        else:
            execution_target, assistant_summary, tool_call_count, execution_status, runtime_session_id, runtime_step_id = self._dispatch_execution(
                session,
                target=target,
                user_message=request.user_message,
                created_at=created_at,
                allow_side_effects=allow_side_effects,
                client_command=client_command,
            )
            target = execution_target
            if request.auto_compact and session.memory_profile.recommended_action == "refresh" and memory_action == "none":
                memory_action = "refreshed"
                self._append_event(
                    session,
                    kind="memory_optimized",
                    detail="Memory profile recommended a prompt/context refresh before deeper execution.",
                    created_at=created_at,
                )
        turn = QueryTurn(
            turn_id=_make_id("turn", f"{session.task_id}-{session.agent_id}-{len(session.turns) + 1}"),
            status="completed" if execution_status != "blocked" else "failed",
            user_message=request.user_message,
            assistant_summary=assistant_summary,
            operation_id=client_command.operation_id,
            tool_call_count=tool_call_count,
            execution_target=target,
            execution_status=execution_status,
            runtime_session_id=runtime_session_id,
            runtime_step_id=runtime_step_id,
            memory_action=memory_action,
            created_at=created_at,
        )
        session.turns.append(turn)
        session.updated_at = created_at
        session.status = "completed" if execution_status != "blocked" else "failed"
        self._append_event(
            session,
            kind="turn_executed",
            detail=f"Executed turn against target '{target}' with status '{execution_status}'.",
            created_at=created_at,
            turn_id=turn.turn_id,
        )
        session.metadata["last_turn_summary"] = turn.assistant_summary
        session.metadata["last_memory_recall_summary"] = session.memory_profile.recall_summary
        self._profiles.update_memory_profile(session)
        session.governance = self._build_governance(session, user_message=request.user_message, client_command=client_command)
        if request.auto_compact and session.memory_profile.recommended_action == "compact":
            self.compact_session(
                session_id,
                QuerySessionCompactRequest(retain_turns=2, title="Automatic Session Compaction"),
                created_at=created_at,
            )
            if session.turns:
                session.turns[-1].memory_action = "compacted"
            self._append_event(
                session,
                kind="memory_optimized",
                detail="Automatic compaction executed because session context pressure became high.",
                created_at=created_at,
            )
            session.governance = self._build_governance(session, user_message=request.user_message, client_command=client_command)
        self._enforce_session_budget(session, created_at=created_at)
        return session

    def record_turn(
        self,
        session_id: str,
        request: QueryTurnRecordRequest,
        *,
        created_at: str,
    ) -> QuerySession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        turn = QueryTurn(
            turn_id=_make_id("turn", f"{session.task_id}-{session.agent_id}-{len(session.turns) + 1}"),
            status=request.status,
            user_message=request.user_message,
            assistant_summary=request.assistant_summary,
            tool_call_count=request.tool_call_count,
            created_at=created_at,
        )
        session.turns.append(turn)
        session.updated_at = created_at
        session.status = "completed" if request.status != "failed" else "failed"
        self._append_event(
            session,
            kind="turn_recorded",
            detail="Query turn recorded for the active session.",
            created_at=created_at,
            turn_id=turn.turn_id,
        )
        self._profiles.update_memory_profile(session)
        self._enforce_session_budget(session, created_at=created_at)
        return session

    def mark_session_running(
        self,
        session_id: str,
        *,
        user_message: str,
        created_at: str,
    ) -> QuerySession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        client_command = self._executor.resolve_client_command(
            user_message,
            permission_mode=normalize_runtime_permission_mode(str(session.metadata.get("permission_mode") or "approval")),
        )
        session.status = "running"
        session.updated_at = created_at
        self._append_event(
            session,
            kind="client_command_planned",
            detail=(f"Agent execution started for operation '{client_command.operation_id}' against target '{client_command.execution_target}'."),
            created_at=created_at,
        )
        session.governance = self._build_governance(
            session,
            user_message=user_message,
            client_command=client_command,
        )
        return session

    def record_agent_execution(
        self,
        session_id: str,
        *,
        user_message: str,
        assistant_summary: str,
        tool_call_count: int,
        execution_target: str | None,
        execution_status: str,
        runtime_provider: str | None,
        runtime_session_id: str | None,
        runtime_step_id: str | None,
        created_at: str,
    ) -> QuerySession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None

        client_command = self._executor.resolve_client_command(
            user_message,
            permission_mode=normalize_runtime_permission_mode(str(session.metadata.get("permission_mode") or "approval")),
        )
        if execution_target is not None and client_command.execution_target != execution_target:
            client_command = client_command.model_copy(update={"execution_target": execution_target})

        turn_status = "failed" if execution_status == "blocked" else "completed"
        turn = QueryTurn(
            turn_id=_make_id("turn", f"{session.task_id}-{session.agent_id}-{len(session.turns) + 1}"),
            status=turn_status,
            user_message=user_message,
            assistant_summary=assistant_summary,
            operation_id=client_command.operation_id,
            tool_call_count=tool_call_count,
            execution_target=execution_target,
            execution_status=execution_status,
            runtime_provider=runtime_provider,
            runtime_session_id=runtime_session_id,
            runtime_step_id=runtime_step_id,
            created_at=created_at,
        )
        session.turns.append(turn)
        session.updated_at = created_at
        session.status = "completed" if turn_status != "failed" else "failed"
        self._append_event(
            session,
            kind="turn_executed",
            detail=f"Recorded external agent execution with status '{execution_status}'.",
            created_at=created_at,
            turn_id=turn.turn_id,
        )
        session.metadata["last_turn_summary"] = assistant_summary
        session.metadata["last_execution_target"] = execution_target
        session.metadata["last_runtime_provider"] = runtime_provider
        session.metadata["last_runtime_session_id"] = runtime_session_id
        session.metadata["last_runtime_step_id"] = runtime_step_id
        self._profiles.update_memory_profile(session)
        session.governance = self._build_governance(
            session,
            user_message=user_message,
            client_command=client_command,
        )
        self._enforce_session_budget(session, created_at=created_at)
        return session

    def compact_session(
        self,
        session_id: str,
        request: QuerySessionCompactRequest,
        *,
        created_at: str,
    ) -> QuerySession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        retained_turns = max(request.retain_turns, 1)
        compacted_turns = session.turns[:-retained_turns] if len(session.turns) > retained_turns else session.turns[:-1]
        if not compacted_turns:
            compacted_turns = session.turns[:-1]
        if not compacted_turns:
            compacted_turns = session.turns
        summary_lines: list[str] = []
        open_items: list[str] = []
        for turn in compacted_turns:
            summary = turn.assistant_summary or turn.user_message
            summary_lines.append(f"- {summary}")
            if turn.status in {"planned", "running", "failed"}:
                open_items.append(turn.user_message)
        summary = QuerySessionSummary(
            summary_id=_make_id("query-summary", f"{session_id}-{len(session.summaries) + 1}"),
            session_id=session_id,
            kind="compaction",
            title=request.title,
            content="\n".join(summary_lines) or "- No historical turns were available for compaction.",
            open_items=open_items,
            quality_score=self._score_summary("\n".join(summary_lines), open_items)[0],
            quality_notes=self._score_summary("\n".join(summary_lines), open_items)[1],
            created_at=created_at,
        )
        session.summaries.append(summary)
        session.metadata["last_compaction_summary_id"] = summary.summary_id
        session.metadata["compaction_count"] = len(session.summaries)
        session.metadata["archived_turn_count"] = session.metadata.get("archived_turn_count", 0) + len(compacted_turns)
        session.metadata["last_memory_recall_summary"] = self._profiles.truncate_text(summary.content, limit=240)
        if len(session.turns) > retained_turns:
            session.turns = session.turns[-retained_turns:]
        elif len(session.turns) > 1:
            session.turns = session.turns[-1:]
        previous_section_index = next(
            (index for index, section in enumerate(session.prompt_sections) if section.section_id.startswith("previous-summary-")),
            None,
        )
        promoted_summary = summary.model_copy(update={"kind": "previous_session"})
        previous_summary_section = self._profiles.build_previous_summary_section(promoted_summary)
        if previous_section_index is None:
            session.prompt_sections.append(previous_summary_section)
        else:
            session.prompt_sections[previous_section_index] = previous_summary_section
        session.updated_at = created_at
        self._append_event(session, kind="session_compacted", detail=f"Compacted session history into summary '{summary.summary_id}'.", created_at=created_at)
        self._append_event(session, kind="summary_promoted", detail="Latest compaction summary promoted into the next-session prompt section.", created_at=created_at)
        session.assembled_system_prompt = self._profiles.assemble_system_prompt(session.prompt_sections)
        self._profiles.update_memory_profile(session)
        session.governance = self._build_governance(
            session,
            user_message=session.current_goal,
            client_command=self._executor.resolve_client_command(
                session.current_goal,
                permission_mode=normalize_runtime_permission_mode(str(session.metadata.get("permission_mode") or "approval")),
            ),
        )
        return session

    def _agent_permission_mode(self, workspace, agent) -> str:
        workspace_metadata = getattr(workspace, "metadata", {}) or {}
        workspace_default = str(workspace_metadata.get("default_permission_mode") or "").strip()
        if workspace_default:
            return normalize_runtime_permission_mode(workspace_default)
        linked_card_id = getattr(agent, "linked_card_id", None)
        linked_card = next((card for card in workspace.card_graph.cards if getattr(card, "card_id", None) == linked_card_id), None)
        if linked_card is not None:
            mode = getattr(linked_card, "permission_mode", "approval")
            return normalize_runtime_permission_mode(str(mode))
        agent_metadata = getattr(agent, "metadata", {}) or {}
        mode = str(agent_metadata.get("permission_mode") or "approval")
        return normalize_runtime_permission_mode(mode)

    def _build_task_analysis(self, workspace, agent, prompt_stack, *, session_id: str):
        return self._profiles.build_task_analysis(
            workspace,
            agent,
            prompt_stack,
            session_id=session_id,
            permission_mode=self._agent_permission_mode(workspace, agent),
        )

    def _build_memory_layers(self, workspace, previous_summary, *, session_id: str):
        return self._profiles.build_memory_layers(workspace, previous_summary, session_id=session_id)

    def _dispatch_execution(
        self,
        session: QuerySession,
        *,
        target: str,
        user_message: str,
        created_at: str,
        allow_side_effects: bool,
        client_command: QueryClientCommand,
    ):
        if target == "browser_runtime":
            return self._executor.execute_browser_target(session, user_message, created_at=created_at, client_command=client_command)
        if target == "research_runtime":
            return self._executor.execute_research_target(session, user_message, created_at=created_at)
        if target == "system_execution":
            return self._executor.execute_system_target(
                session,
                user_message,
                allow_side_effects=allow_side_effects,
                client_command=client_command,
            )
        return self._executor.execute_read_target(session, user_message, client_command=client_command)

    def _build_governance(
        self,
        session: QuerySession,
        *,
        user_message: str,
        client_command: QueryClientCommand,
    ) -> QuerySessionGovernance:
        return build_session_governance(
            current_goal=session.current_goal,
            user_message=user_message,
            memory_profile=session.memory_profile,
            active_operation=client_command,
            continuation_source=str(session.metadata.get("continuation_source") or "").strip() or None,
            previous_session_id=str(session.metadata.get("previous_session_id") or "").strip() or None,
            archived_turn_count=int(session.metadata.get("archived_turn_count", 0)),
        )

    def _append_event(
        self,
        session: QuerySession,
        *,
        kind: str,
        detail: str,
        created_at: str,
        turn_id: str | None = None,
    ) -> None:
        session.runtime_events.append(
            QueryRuntimeEvent(
                event_id=_make_id("query-event", f"{session.session_id}-{len(session.runtime_events) + 1}"),
                session_id=session.session_id,
                turn_id=turn_id,
                kind=kind,
                detail=detail,
                created_at=created_at,
            )
        )
        if len(session.runtime_events) > self._max_runtime_events:
            session.runtime_events = session.runtime_events[: self._max_runtime_events]

    def _enforce_session_budget(self, session: QuerySession, *, created_at: str) -> None:
        if len(session.turns) > self._max_active_turns:
            self.compact_session(
                session.session_id,
                QuerySessionCompactRequest(
                    retain_turns=max(2, min(4, self._max_active_turns // 2)),
                    title="Runtime Maintenance Compaction",
                ),
                created_at=created_at,
            )
        if len(session.summaries) > self._max_summaries:
            session.summaries = session.summaries[-self._max_summaries :]
            session.metadata["summary_retention_applied_at"] = created_at
        if len(session.runtime_events) > self._max_runtime_events:
            session.runtime_events = session.runtime_events[: self._max_runtime_events]
            session.metadata["runtime_event_retention_applied_at"] = created_at

    def _score_summary(self, content: str, open_items: list[str]) -> tuple[float, list[str]]:
        stripped = content.strip()
        notes: list[str] = []
        if not stripped:
            notes.append("empty_summary")
        if len(stripped) < 80:
            notes.append("short_summary")
        if "- " not in stripped and "\n" not in stripped:
            notes.append("low_structure")
        if len(open_items) > 5:
            notes.append("many_open_items")
        lower = stripped.lower()
        if stripped.count("...") > 3 or lower.count("todo") > 8:
            notes.append("placeholder_or_todo_heavy")
        if open_items and not any(token in lower for token in ("next", "blocked", "todo", "follow", "继续", "下一步")):
            notes.append("open_items_not_reflected")
        score = 1.0
        score -= 0.25 * len(notes)
        if 120 <= len(stripped) <= 4000:
            score += 0.1
        return max(0.0, min(1.0, round(score, 2))), notes


_service = QueryEngineService()


def get_query_engine_service() -> QueryEngineService:
    return _service
