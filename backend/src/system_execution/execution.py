"""Execution helpers for system execution sessions."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .contracts import (
    SystemExecutionAuditEntry,
    SystemExecutionDesktopSnapshot,
    SystemExecutionSession,
    SystemExecutionStepExecutionRequest,
    SystemExecutionStepExecutionResult,
)
from .policy import SystemExecutionPolicyEngine


class SystemExecutionRuntimeExecutor:
    """Execute bounded system-execution steps within current system limits."""

    def __init__(
        self,
        *,
        policy: SystemExecutionPolicyEngine,
        workspace_root_fn=None,
        subprocess_module=subprocess,
        open_command_fn=None,
    ):
        self._policy = policy
        self._workspace_root_fn = workspace_root_fn or policy.workspace_root
        self._subprocess = subprocess_module
        self._open_command_fn = open_command_fn or self.system_open_command

    def truncate_output(self, value: str, *, limit: int = 1200) -> str:
        if len(value) <= limit:
            return value
        return f"{value[:limit]}...(truncated)"

    def system_open_command(self, target: Path) -> list[str] | None:
        if sys.platform == "darwin":
            opener = shutil.which("open")
            return [opener, str(target)] if opener else None
        if sys.platform.startswith("win"):
            return ["cmd", "/c", "start", "", str(target)]
        opener = shutil.which("xdg-open")
        return [opener, str(target)] if opener else None

    def open_workspace_target(self, path_value: str) -> tuple[str, str, str]:
        path = Path(path_value)
        if not path.is_absolute():
            path = self._workspace_root_fn() / path
        path = path.resolve()
        try:
            path.relative_to(self._workspace_root_fn().resolve())
        except ValueError:
            return "blocked", f"Blocked path outside workspace policy: {path}", str(path)
        if not path.exists():
            return "blocked", f"Requested path does not exist: {path}", str(path)
        command = self._open_command_fn(path)
        if command is None:
            return "blocked", f"No system opener is available for path handoff: {path}", str(path)
        self._subprocess.Popen(command, cwd=str(self._workspace_root_fn()))
        return "completed", f"Opened workspace target: {path}", str(path)

    def launch_allowed_app(self, app_name: str) -> tuple[str, str]:
        app_binary = shutil.which(app_name)
        if app_binary is None:
            return "blocked", f"Allowed app is not available on this host: {app_name}"
        self._subprocess.Popen([app_binary], cwd=str(self._workspace_root_fn()))
        return "completed", f"Launched allowed app: {app_name}"

    def run_safe_command(self, command: str, *, cwd: Path) -> tuple[str, str, int]:
        completed = self._subprocess.run(
            ["bash", "-lc", command],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        combined = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
        if not combined:
            combined = "(no output)"
        if completed.returncode == 0:
            return "completed", self.truncate_output(combined), completed.returncode
        return "blocked", self.truncate_output(f"command exited with {completed.returncode}: {combined}"), completed.returncode

    def execute_next_step(
        self,
        session: SystemExecutionSession,
        request: SystemExecutionStepExecutionRequest,
        *,
        timestamp: str,
        snapshot: SystemExecutionDesktopSnapshot | None,
    ) -> tuple[SystemExecutionStepExecutionResult, SystemExecutionAuditEntry, SystemExecutionDesktopSnapshot | None]:
        next_step = next(
            (step for step in session.plan.steps if step.id not in session.completed_step_ids),
            None,
        )
        if next_step is None:
            session.status = "ready" if session.dry_run else "running"
            session.updated_at = timestamp
            self._policy.refresh_pending_state(session)
            return (
                SystemExecutionStepExecutionResult(
                    session_id=session.session_id,
                    step_id="none",
                    status="completed",
                    detail="No remaining system execution steps to execute.",
                    remaining_steps=0,
                    last_command=session.last_command,
                    last_exit_code=session.last_exit_code,
                    last_output=session.last_output,
                    recovery_available=False,
                ),
                SystemExecutionAuditEntry(
                    session_id=session.session_id,
                    step_id="none",
                    action_kind="verify_state",
                    status="completed",
                    detail="No remaining system execution steps to execute.",
                    timestamp=timestamp,
                ),
                snapshot,
            )

        session.status = "running"
        session.updated_at = timestamp
        detail = request.note or f"Simulated system execution step '{next_step.id}'."
        result_status = "simulated"
        step_completed = True

        if not session.dry_run and next_step.kind == "open":
            result_status, detail, snapshot = self._execute_open_step(session, timestamp, snapshot)
            step_completed = result_status != "blocked"
        elif not session.dry_run and next_step.kind == "act" and session.requested_commands:
            result_status, detail, step_completed, snapshot = self._execute_command_step(session, timestamp, snapshot)

        if step_completed:
            session.completed_step_ids.append(next_step.id)
        remaining_steps = len(session.plan.steps) - len(session.completed_step_ids)
        if result_status == "blocked":
            session.status = "blocked"
        self._policy.refresh_pending_state(session)
        if remaining_steps == 0:
            session.status = "ready" if session.dry_run else "running"
            self._policy.refresh_pending_state(session)

        audit = SystemExecutionAuditEntry(
            session_id=session.session_id,
            step_id=next_step.id,
            action_kind=(next_step.actions[0].kind if next_step.actions else "verify_state"),
            status=result_status if not session.dry_run else "simulated",
            detail=detail,
            timestamp=timestamp,
        )
        result = SystemExecutionStepExecutionResult(
            session_id=session.session_id,
            step_id=next_step.id,
            status=result_status,
            detail=detail,
            remaining_steps=remaining_steps,
            last_command=session.last_command,
            last_exit_code=session.last_exit_code,
            last_output=session.last_output,
            recovery_available=session.recovery_available,
        )
        return result, audit, snapshot

    def _execute_open_step(
        self,
        session: SystemExecutionSession,
        timestamp: str,
        snapshot: SystemExecutionDesktopSnapshot | None,
    ) -> tuple[str, str, SystemExecutionDesktopSnapshot | None]:
        if session.target == "filesystem" and session.requested_paths:
            next_path_index = min(len(session.opened_targets), len(session.requested_paths) - 1)
            path_value = session.requested_paths[next_path_index]
            result_status, detail, resolved_target = self.open_workspace_target(path_value)
            if result_status == "completed":
                session.opened_targets.append(resolved_target)
                snapshot = self._update_snapshot(
                    snapshot,
                    timestamp=timestamp,
                    active_app="system-opener",
                    active_window="workspace-target",
                    focused_target=resolved_target,
                    screen_summary=detail,
                )
            else:
                session.last_output = detail
                session.last_blocked_reason = detail
                snapshot = self._update_snapshot(snapshot, timestamp=timestamp, screen_summary=detail)
            return result_status, detail, snapshot
        if session.target in {"desktop", "hybrid"} and session.allowed_apps:
            next_app_index = min(len(session.launched_apps), len(session.allowed_apps) - 1)
            app_name = session.allowed_apps[next_app_index]
            result_status, detail = self.launch_allowed_app(app_name)
            if result_status == "completed":
                session.launched_apps.append(app_name)
                snapshot = self._update_snapshot(
                    snapshot,
                    timestamp=timestamp,
                    active_app=app_name,
                    active_window=app_name,
                    focused_target=app_name,
                    screen_summary=detail,
                )
            else:
                session.last_output = detail
                session.last_blocked_reason = detail
                snapshot = self._update_snapshot(snapshot, timestamp=timestamp, screen_summary=detail)
            return result_status, detail, snapshot
        return "simulated", "No live open target was requested for this step.", snapshot

    def _execute_command_step(
        self,
        session: SystemExecutionSession,
        timestamp: str,
        snapshot: SystemExecutionDesktopSnapshot | None,
    ) -> tuple[str, str, bool, SystemExecutionDesktopSnapshot | None]:
        next_command_index = len(session.executed_commands)
        command = (
            session.requested_commands[-1]
            if next_command_index >= len(session.requested_commands)
            else session.requested_commands[next_command_index]
        )
        working_directory = self._policy.working_directory_for_target(session.target)
        session.last_command = command
        if session.plan.blocked_reasons:
            detail = session.plan.blocked_reasons[0]
            session.last_blocked_reason = detail
            session.last_output = detail
            session.last_exit_code = None
            snapshot = self._update_snapshot(snapshot, timestamp=timestamp, screen_summary=detail)
            return "blocked", detail, False, snapshot
        if not self._policy.is_safe_read_command(command):
            detail = f"Blocked command outside safe-read policy: {command}"
            session.last_blocked_reason = detail
            session.last_output = detail
            session.last_exit_code = None
            snapshot = self._update_snapshot(snapshot, timestamp=timestamp, screen_summary=detail)
            return "blocked", detail, False, snapshot

        result_status, command_output, exit_code = self.run_safe_command(command, cwd=working_directory)
        session.last_output = command_output
        session.last_exit_code = exit_code
        session.last_blocked_reason = None if result_status == "completed" else command_output
        session.executed_commands.append(command)
        remaining_commands = len(session.requested_commands) - len(session.executed_commands)
        if remaining_commands > 0:
            detail = (
                f"Executed command in {working_directory}: {command}\n{command_output}\n"
                f"{remaining_commands} requested command(s) remain in this act step."
            )
            step_completed = False
        else:
            detail = f"Executed command in {working_directory}: {command}\n{command_output}"
            step_completed = result_status != "blocked"
        snapshot = self._update_snapshot(
            snapshot,
            timestamp=timestamp,
            active_app="shell",
            active_window="bounded-shell",
            focused_target=str(working_directory),
            screen_summary=f"Executed safe command '{command}'.",
        )
        return result_status, detail, step_completed, snapshot

    def _update_snapshot(
        self,
        snapshot: SystemExecutionDesktopSnapshot | None,
        *,
        timestamp: str,
        active_app: str | None = None,
        active_window: str | None = None,
        focused_target: str | None = None,
        screen_summary: str,
    ) -> SystemExecutionDesktopSnapshot | None:
        if snapshot is None:
            return None
        if active_app is not None:
            snapshot.active_app = active_app
        if active_window is not None:
            snapshot.active_window = active_window
        if focused_target is not None:
            snapshot.focused_target = focused_target
        snapshot.screen_summary = screen_summary
        snapshot.timestamp = timestamp
        return snapshot
