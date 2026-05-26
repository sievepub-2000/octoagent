"""Conservative provider used when system execution is not enabled."""

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


class NoneSystemExecutionProvider(BaseSystemExecutionProvider):
    name = "none"

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
            note=cfg.note,
        )

    def plan(self, request: SystemExecutionPlanRequest) -> SystemExecutionPlan:
        capability = self.get_capability()
        missing: list[str] = []
        notes: list[str] = []

        if request.target in {"desktop", "hybrid"} and not capability.supports_desktop_control:
            missing.append("desktop_control")
        if request.target in {"desktop", "hybrid"} and not capability.supports_window_introspection:
            missing.append("window_introspection")
        if request.target in {"filesystem", "hybrid"} and not capability.supports_file_open_handoffs:
            missing.append("file_open_handoffs")
        if request.target in {"browser", "hybrid"} and not capability.supports_browser_handoff:
            missing.append("browser_handoff")

        status = "blocked" if missing else ("ready" if capability.enabled else "planned")
        if not capability.enabled:
            notes.append("System execution runtime is not enabled; plan remains a dry-run contract.")
        if request.allowed_apps:
            notes.append("Allowed apps: " + ", ".join(request.allowed_apps[:8]))
        if request.expected_outcome:
            notes.append(f"Expected outcome: {request.expected_outcome}")

        steps = [
            SystemExecutionStep(
                id="system-exec-inspect",
                title="Inspect target environment",
                description="Capture current window/application context before acting.",
                kind="inspect",
                requires_approval=request.require_approval,
                actions=[SystemExecutionAction(kind="inspect_screen")],
            ),
            SystemExecutionStep(
                id="system-exec-focus",
                title="Focus target surface",
                description="Move control to the intended desktop, browser, or filesystem surface.",
                kind="focus",
                requires_approval=request.require_approval,
                actions=[
                    SystemExecutionAction(
                        kind="focus_window",
                        target=request.target,
                    )
                ],
            ),
            SystemExecutionStep(
                id="system-exec-act",
                title="Perform bounded action",
                description=f"Execute a bounded action sequence for goal: {request.goal}",
                kind="act",
                requires_approval=request.require_approval,
                actions=[
                    SystemExecutionAction(
                        kind="verify_state",
                        value=request.goal,
                    )
                ],
            ),
            SystemExecutionStep(
                id="system-exec-verify",
                title="Verify expected outcome",
                description="Check that the resulting system state matches the requested outcome.",
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

        return SystemExecutionPlan(
            engine=capability.engine,
            status=status,
            target=request.target,
            steps=steps,
            missing_capabilities=missing,
            notes=notes,
        )
