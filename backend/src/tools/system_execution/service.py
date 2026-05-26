"""Service layer for system-level execution skeleton."""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .contracts import (
    SystemExecutionAuditEntry,
    SystemExecutionCliRequest,
    SystemExecutionCliResponse,
    SystemExecutionDesktopSnapshot,
    SystemExecutionPermissionPolicy,
    SystemExecutionPlan,
    SystemExecutionPlanRequest,
    SystemExecutionSession,
    SystemExecutionSessionRecoveryRequest,
    SystemExecutionSessionUpdateRequest,
    SystemExecutionStepExecutionRequest,
    SystemExecutionStepExecutionResult,
)
from .execution import SystemExecutionRuntimeExecutor
from .governance import evaluate_system_operation_governance
from .policy import SystemExecutionPolicyEngine
from .registry import get_system_execution_provider
from .store import SystemExecutionStore

__all__ = ["SystemExecutionService", "shutil"]


class SystemExecutionService:
    """Resolve the configured provider and expose a stable service facade."""

    def __init__(self):
        self._store = SystemExecutionStore()
        self._policy = SystemExecutionPolicyEngine()
        self._execution = SystemExecutionRuntimeExecutor(
            policy=self._policy,
            workspace_root_fn=self._workspace_root,
            subprocess_module=subprocess,
            open_command_fn=self._system_open_command,
        )

    def _provider(self):
        return get_system_execution_provider()

    def _utc_now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _workspace_root(self) -> Path:
        return self._policy.workspace_root()

    def _system_open_command(self, target: Path) -> list[str] | None:
        return self._execution.system_open_command(target)

    def get_permission_policy(self) -> SystemExecutionPermissionPolicy:
        return self._policy.get_permission_policy()

    def get_capability(self):
        capability = self._provider().get_capability()
        capability.supports_permission_policies = True
        return capability

    def plan(self, request: SystemExecutionPlanRequest) -> SystemExecutionPlan:
        plan = self._provider().plan(request)
        blocked_reasons = self._policy.evaluate_request(request)
        plan.permission_policy = self.get_permission_policy()
        plan.blocked_reasons = blocked_reasons
        if blocked_reasons:
            plan.status = "blocked"
            plan.notes.append("Permission policy blocked one or more requested commands.")
        return plan

    def create_session(
        self,
        request: SystemExecutionPlanRequest,
        *,
        dry_run: bool = True,
    ) -> SystemExecutionSession:
        provider = self._provider()
        session = provider.create_session(request, dry_run=dry_run)
        session.plan = self.plan(request)
        session.updated_at = self._utc_now()
        session.completed_step_ids = []
        session.last_blocked_reason = None
        self._policy.refresh_pending_state(session)
        self._store.save_session(session)
        self._store.save_snapshot(provider.build_snapshot(session))
        self._store.append_audits(session.session_id, provider.build_audit_entries(session))
        return session

    def get_session(self, session_id: str) -> SystemExecutionSession | None:
        return self._store.get_session(session_id)

    def list_sessions(
        self,
        *,
        target: str | None = None,
        related_task_id: str | None = None,
        limit: int = 20,
    ) -> list[SystemExecutionSession]:
        return self._store.list_sessions(
            target=target,
            related_task_id=related_task_id,
            limit=limit,
        )

    def get_snapshot(self, session_id: str) -> SystemExecutionDesktopSnapshot | None:
        return self._store.get_snapshot(session_id)

    def get_audits(self, session_id: str) -> list[SystemExecutionAuditEntry]:
        return self._store.get_audits(session_id)

    def update_session(
        self,
        session_id: str,
        request: SystemExecutionSessionUpdateRequest,
    ) -> SystemExecutionSession | None:
        session = self._store.get_session(session_id)
        if session is None:
            return None
        session.status = request.status
        session.updated_at = self._utc_now()
        if request.status != "blocked":
            session.last_blocked_reason = None
        self._policy.refresh_pending_state(session)
        self._store.save_session(session)
        self._store.append_audits(
            session_id,
            [
                SystemExecutionAuditEntry(
                    session_id=session_id,
                    step_id="session-status",
                    action_kind="verify_state",
                    status="simulated" if session.dry_run else "planned",
                    detail=request.detail or f"System execution session moved to '{request.status}'.",
                    timestamp=session.updated_at,
                )
            ],
        )
        return session

    def recover_session(
        self,
        session_id: str,
        request: SystemExecutionSessionRecoveryRequest,
    ) -> SystemExecutionSession | None:
        session = self._store.get_session(session_id)
        if session is None:
            return None
        self._policy.refresh_pending_state(session)
        if not session.recovery_available:
            return session
        session.status = "ready" if session.dry_run else "planned"
        session.updated_at = self._utc_now()
        session.last_blocked_reason = None
        session.last_output = None
        self._policy.refresh_pending_state(session)
        self._store.save_session(session)
        self._store.append_audits(
            session_id,
            [
                SystemExecutionAuditEntry(
                    session_id=session_id,
                    step_id="session-recover",
                    action_kind="verify_state",
                    status="planned" if not session.dry_run else "simulated",
                    detail=request.note or "System execution session recovered for retry.",
                    timestamp=session.updated_at,
                )
            ],
        )
        return session

    def execute_next_step(
        self,
        session_id: str,
        request: SystemExecutionStepExecutionRequest,
    ) -> SystemExecutionStepExecutionResult | None:
        session = self._store.get_session(session_id)
        if session is None:
            return None
        self._execution._workspace_root_fn = self._workspace_root
        self._execution._open_command_fn = self._system_open_command
        self._execution._subprocess = subprocess
        snapshot = self._store.get_snapshot(session_id)
        result, audit, snapshot = self._execution.execute_next_step(
            session,
            request,
            timestamp=self._utc_now(),
            snapshot=snapshot,
        )
        self._store.save_session(session)
        if snapshot is not None:
            self._store.save_snapshot(snapshot)
        self._store.append_audits(session_id, [audit])
        return result

    def execute_cli_command(
        self,
        request: SystemExecutionCliRequest,
        *,
        scope: str,
    ) -> SystemExecutionCliResponse:
        target = "system_cli" if scope == "system" else "workspace_cli"
        session = self.create_session(
            SystemExecutionPlanRequest(
                goal=f"Run {scope} CLI command",
                target=target,
                require_approval=request.require_approval,
                requested_commands=[request.command],
                expected_outcome=request.command,
            ),
            dry_run=False,
        )
        session.related_task_id = request.task_id
        session.related_task_name = request.task_name
        self._store.save_session(session)
        governance = evaluate_system_operation_governance(
            command=request.command,
            require_approval=request.require_approval,
            actor=request.actor,
            role=request.role,
        )
        self._store.append_audits(
            session.session_id,
            [
                SystemExecutionAuditEntry(
                    session_id=session.session_id,
                    step_id="operator-governance",
                    action_kind="verify_state",
                    status="planned" if governance.allowed else "blocked",
                    detail=governance.reason,
                    timestamp=self._utc_now(),
                    details=governance.audit_event,
                )
            ],
        )
        if not governance.allowed:
            session.status = "blocked"
            session.last_blocked_reason = governance.reason
            session.last_output = governance.reason
            session.recovery_available = True
            self._policy.refresh_pending_state(session)
            self._store.save_session(session)
            latest_result = SystemExecutionStepExecutionResult(
                session_id=session.session_id,
                step_id="operator-governance",
                status="blocked",
                detail=governance.reason,
                remaining_steps=len(session.pending_step_ids),
                last_command=request.command,
                last_exit_code=None,
                last_output=governance.reason,
                recovery_available=session.recovery_available,
            )
            return SystemExecutionCliResponse(session=session, result=latest_result)
        latest_result: SystemExecutionStepExecutionResult | None = None
        for _ in range(max(1, len(session.plan.steps) + 1)):
            latest_result = self.execute_next_step(
                session.session_id,
                SystemExecutionStepExecutionRequest(note=request.note or request.command),
            )
            if latest_result is None:
                break
            if latest_result.last_command is not None or latest_result.status == "blocked" or latest_result.remaining_steps == 0:
                break
        loaded_session = self.get_session(session.session_id) or session
        if latest_result is None:
            latest_result = SystemExecutionStepExecutionResult(
                session_id=loaded_session.session_id,
                step_id="none",
                status="blocked",
                detail="CLI execution did not return a runtime result.",
                remaining_steps=len(loaded_session.pending_step_ids),
                last_command=loaded_session.last_command,
                last_exit_code=loaded_session.last_exit_code,
                last_output=loaded_session.last_output,
                recovery_available=loaded_session.recovery_available,
            )
        return SystemExecutionCliResponse(session=loaded_session, result=latest_result)


_service = SystemExecutionService()


def get_system_execution_service() -> SystemExecutionService:
    return _service
