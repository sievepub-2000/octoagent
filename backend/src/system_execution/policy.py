"""Policy helpers for system execution planning and session state."""

from __future__ import annotations

from pathlib import Path

from src.config.integrations_config import get_integrations_config
from src.config.paths import get_paths

from .contracts import (
    SystemExecutionPermissionPolicy,
    SystemExecutionPermissionRule,
    SystemExecutionPlanRequest,
    SystemExecutionSession,
)


class SystemExecutionPolicyEngine:
    """Encapsulate permission policy and workspace-bound safety checks."""

    def _system_execution_config(self):
        return get_integrations_config().system_execution

    def workspace_root(self) -> Path:
        return get_paths().base_dir

    def system_root(self) -> Path:
        return Path.home().resolve()

    def working_directory_for_target(self, target: str) -> Path:
        if target == "system_cli":
            return self.system_root()
        return self.workspace_root()

    def path_within_workspace(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.workspace_root().resolve())
        except ValueError:
            return False
        return True

    def resolve_requested_path(self, path_value: str) -> Path:
        path = Path(path_value)
        if not path.is_absolute():
            path = self.workspace_root() / path
        return path.resolve()

    def is_allowed_requested_path(self, path_value: str) -> bool:
        return self.path_within_workspace(self.resolve_requested_path(path_value))

    def refresh_pending_state(self, session: SystemExecutionSession) -> None:
        session.pending_step_ids = [
            step.id for step in session.plan.steps if step.id not in session.completed_step_ids
        ]
        session.recovery_available = session.status == "blocked" and bool(session.pending_step_ids)

    def get_permission_policy(self) -> SystemExecutionPermissionPolicy:
        config = self._system_execution_config()
        return SystemExecutionPermissionPolicy(
            policy_id=config.permission_policy.policy_id,
            title=config.permission_policy.title,
            default_effect=config.permission_policy.default_effect,
            rules=[
                SystemExecutionPermissionRule(
                    rule_id=rule.rule_id,
                    scope=rule.scope,
                    effect=rule.effect,
                    match_prefixes=list(rule.match_prefixes),
                    match_values=list(rule.match_values),
                    note=rule.note,
                )
                for rule in config.permission_policy.rules
            ],
        )

    def is_safe_read_command(self, command: str) -> bool:
        for rule in self.get_permission_policy().rules:
            if rule.scope != "shell":
                continue
            if any(command.startswith(prefix) for prefix in rule.match_prefixes):
                return rule.effect == "allow"
        return False

    def evaluate_request(self, request: SystemExecutionPlanRequest) -> list[str]:
        blocked: list[str] = []
        if request.target == "system_cli" and not self._system_execution_config().system_cli_enabled:
            blocked.append("System CLI is disabled by configuration")
        policy = self.get_permission_policy()
        for command in request.requested_commands:
            matched = False
            for rule in policy.rules:
                if rule.scope != "shell":
                    continue
                if any(command.startswith(prefix) for prefix in rule.match_prefixes):
                    matched = True
                    if rule.effect == "deny":
                        blocked.append(f"Command '{command}' blocked by policy rule '{rule.rule_id}'")
                    break
            if request.target in {"workspace_cli", "system_cli"} and not matched:
                blocked.append(f"Command '{command}' is outside the bounded CLI allowlist")
        for path_value in request.requested_paths:
            if not self.is_allowed_requested_path(path_value):
                blocked.append(f"Path '{path_value}' blocked by workspace path policy")
        return blocked
