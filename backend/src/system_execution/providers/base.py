"""Base helpers for system execution providers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.system_execution.contracts import (
    SystemExecutionAuditEntry,
    SystemExecutionCapability,
    SystemExecutionDesktopSnapshot,
    SystemExecutionPlan,
    SystemExecutionPlanRequest,
    SystemExecutionSession,
)


class BaseSystemExecutionProvider:
    name = "base"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def get_capability(self) -> SystemExecutionCapability:
        raise NotImplementedError

    def plan(self, request: SystemExecutionPlanRequest) -> SystemExecutionPlan:
        raise NotImplementedError

    def build_snapshot(self, session: SystemExecutionSession) -> SystemExecutionDesktopSnapshot:
        return SystemExecutionDesktopSnapshot(
            session_id=session.session_id,
            active_app=None,
            active_window=None,
            focused_target=session.target,
            screen_summary="No live desktop snapshot available. Session is in planning/dry-run mode.",
            cursor_hint=None,
            timestamp=self._now_iso(),
        )

    def build_audit_entries(self, session: SystemExecutionSession) -> list[SystemExecutionAuditEntry]:
        entries: list[SystemExecutionAuditEntry] = []
        timestamp = self._now_iso()
        for step in session.plan.steps:
            for action in step.actions:
                entries.append(
                    SystemExecutionAuditEntry(
                        session_id=session.session_id,
                        step_id=step.id,
                        action_kind=action.kind,
                        status="simulated" if session.dry_run else "planned",
                        detail=step.description,
                        timestamp=timestamp,
                    )
                )
        return entries

    def create_session(
        self,
        request: SystemExecutionPlanRequest,
        *,
        dry_run: bool = True,
    ) -> SystemExecutionSession:
        plan = self.plan(request)
        status = "planned" if dry_run else plan.status
        return SystemExecutionSession(
            session_id=f"system-exec-{uuid.uuid4()}",
            status=status,
            engine=plan.engine,
            target=plan.target,
            dry_run=dry_run,
            plan=plan,
            allowed_apps=list(request.allowed_apps),
            requested_paths=list(request.requested_paths),
            requested_commands=list(request.requested_commands),
            opened_targets=[],
            launched_apps=[],
            executed_commands=[],
        )
