"""Local desktop provider skeleton for future Agent-S-style execution."""

from __future__ import annotations

from src.runtime.config.integrations_config import get_integrations_config
from src.tools.system_execution.contracts import (
    SystemExecutionAction,
    SystemExecutionCapability,
    SystemExecutionPlan,
    SystemExecutionPlanRequest,
    SystemExecutionStep,
)

from .base import BaseSystemExecutionProvider


class LocalDesktopSystemExecutionProvider(BaseSystemExecutionProvider):
    name = "local_desktop"

    def get_capability(self) -> SystemExecutionCapability:
        cfg = get_integrations_config().system_execution
        browser_cfg = get_integrations_config().browser
        return SystemExecutionCapability(
            enabled=cfg.enabled,
            engine=cfg.engine,
            supports_desktop_control=cfg.supports_desktop_control,
            supports_window_introspection=cfg.supports_window_introspection,
            supports_file_open_handoffs=cfg.supports_file_open_handoffs,
            supports_browser_handoff=browser_cfg.enabled,
            note=("Local desktop provider skeleton only. Planning contracts are implemented, but no live cursor/keyboard/window driver is attached yet."),
        )

    def plan(self, request: SystemExecutionPlanRequest) -> SystemExecutionPlan:
        capability = self.get_capability()
        if request.target in {"workspace_cli", "system_cli"}:
            scope_label = "system" if request.target == "system_cli" else "workspace"
            command_value = request.requested_commands[0] if request.requested_commands else request.goal
            return SystemExecutionPlan(
                engine=capability.engine,
                status="ready",
                target=request.target,
                steps=[
                    SystemExecutionStep(
                        id="cli-inspect",
                        title="Inspect CLI scope",
                        description=f"Confirm bounded {scope_label} CLI scope and command eligibility.",
                        kind="inspect",
                        requires_approval=request.require_approval,
                        actions=[SystemExecutionAction(kind="verify_state", value=f"cli_scope:{scope_label}")],
                    ),
                    SystemExecutionStep(
                        id="cli-exec-act",
                        title="Run bounded CLI command",
                        description=f"Execute a bounded {scope_label} CLI command on the server.",
                        kind="act",
                        requires_approval=request.require_approval,
                        actions=[SystemExecutionAction(kind="run_command", value=command_value)],
                    ),
                    SystemExecutionStep(
                        id="cli-verify",
                        title="Verify CLI outcome",
                        description="Verify the bounded CLI command completed or returned a blocked result.",
                        kind="verify",
                        requires_approval=False,
                        actions=[SystemExecutionAction(kind="verify_state", value=request.expected_outcome or command_value)],
                    ),
                ],
                missing_capabilities=[],
                notes=[
                    f"CLI scope: {scope_label}.",
                    "Server-side CLI execution stays bounded by the shell allowlist and permission policy.",
                ],
            )

        missing: list[str] = []
        if not capability.supports_desktop_control and request.target in {"desktop", "hybrid"}:
            missing.append("desktop_control")
        if not capability.supports_window_introspection and request.target in {"desktop", "hybrid"}:
            missing.append("window_introspection")

        status = "blocked" if missing else "ready"
        steps = [
            SystemExecutionStep(
                id="desktop-inspect",
                title="Inspect desktop state",
                description="Capture screen, active window, and focused application.",
                kind="inspect",
                requires_approval=request.require_approval,
                actions=[
                    SystemExecutionAction(kind="inspect_screen"),
                    SystemExecutionAction(kind="verify_state", value="active_window"),
                ],
            ),
            SystemExecutionStep(
                id="desktop-open",
                title="Open or focus target app",
                description="Launch or foreground the allowed target application.",
                kind="open",
                requires_approval=request.require_approval,
                actions=[
                    SystemExecutionAction(
                        kind="launch_app",
                        target=request.allowed_apps[0] if request.allowed_apps else None,
                    ),
                    SystemExecutionAction(
                        kind="focus_window",
                        target=request.allowed_apps[0] if request.allowed_apps else request.target,
                    ),
                ],
            ),
            SystemExecutionStep(
                id="desktop-act",
                title="Execute bounded UI actions",
                description="Perform approved keyboard, pointer, or file-open actions.",
                kind="act",
                requires_approval=request.require_approval,
                actions=[
                    SystemExecutionAction(kind="click", target="planned_target"),
                    SystemExecutionAction(kind="type", value=request.goal),
                ],
            ),
            SystemExecutionStep(
                id="desktop-verify",
                title="Verify end state",
                description="Check the UI state matches the requested outcome.",
                kind="verify",
                requires_approval=False,
                actions=[
                    SystemExecutionAction(
                        kind="verify_state",
                        value=request.expected_outcome or request.goal,
                    )
                ],
            ),
        ]

        notes = [
            "Provider selected: local_desktop skeleton.",
            "Execution loop is not implemented yet; this plan defines the contract only.",
        ]
        if request.allowed_apps:
            notes.append("Allowed apps: " + ", ".join(request.allowed_apps[:8]))

        return SystemExecutionPlan(
            engine=capability.engine,
            status=status,
            target=request.target,
            steps=steps,
            missing_capabilities=missing,
            notes=notes,
        )
