"""Contracts for system-level execution planning and session state."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SystemExecutionEngine = Literal["none", "sandbox_exec", "desktop_agent", "hybrid"]
SystemExecutionStatus = Literal["unavailable", "planned", "ready", "running", "blocked"]
SystemExecutionTarget = Literal["desktop", "browser", "filesystem", "hybrid", "workspace_cli", "system_cli"]
SystemCliScope = Literal["workspace", "system"]
SystemExecutionActionKind = Literal[
    "inspect_screen",
    "focus_window",
    "launch_app",
    "open_file",
    "run_command",
    "click",
    "type",
    "hotkey",
    "scroll",
    "wait_for",
    "verify_state",
]
SystemPermissionScope = Literal["shell", "filesystem", "browser", "desktop", "runtime"]
SystemPermissionEffect = Literal["allow", "ask", "deny"]


class SystemExecutionCapability(BaseModel):
    enabled: bool = False
    engine: SystemExecutionEngine = "none"
    supports_desktop_control: bool = False
    supports_window_introspection: bool = False
    supports_file_open_handoffs: bool = False
    supports_browser_handoff: bool = False
    supports_permission_policies: bool = True
    note: str = ""


class SystemExecutionPermissionRule(BaseModel):
    rule_id: str
    scope: SystemPermissionScope
    effect: SystemPermissionEffect
    match_prefixes: list[str] = Field(default_factory=list)
    match_values: list[str] = Field(default_factory=list)
    note: str | None = None


class SystemExecutionPermissionPolicy(BaseModel):
    policy_id: str
    title: str
    default_effect: SystemPermissionEffect = "ask"
    rules: list[SystemExecutionPermissionRule] = Field(default_factory=list)


class SystemExecutionPlanRequest(BaseModel):
    goal: str
    target: SystemExecutionTarget = "desktop"
    require_approval: bool = True
    allowed_apps: list[str] = Field(default_factory=list)
    requested_commands: list[str] = Field(default_factory=list)
    requested_paths: list[str] = Field(default_factory=list)
    expected_outcome: str | None = None


class SystemExecutionSessionUpdateRequest(BaseModel):
    status: Literal["ready", "running", "blocked"]
    detail: str = ""


class SystemExecutionSessionRecoveryRequest(BaseModel):
    note: str = ""


class SystemExecutionStepExecutionRequest(BaseModel):
    note: str = ""


class SystemExecutionStepExecutionResult(BaseModel):
    session_id: str
    step_id: str
    status: Literal["simulated", "blocked", "completed"] = "simulated"
    detail: str
    remaining_steps: int
    last_command: str | None = None
    last_exit_code: int | None = None
    last_output: str | None = None
    recovery_available: bool = False


class SystemExecutionAction(BaseModel):
    kind: SystemExecutionActionKind
    target: str | None = None
    value: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class SystemExecutionStep(BaseModel):
    id: str
    title: str
    description: str
    kind: Literal["inspect", "focus", "open", "act", "verify", "handoff"]
    requires_approval: bool = True
    actions: list[SystemExecutionAction] = Field(default_factory=list)


class SystemExecutionPlan(BaseModel):
    engine: SystemExecutionEngine = "none"
    status: SystemExecutionStatus = "planned"
    target: SystemExecutionTarget
    steps: list[SystemExecutionStep] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    permission_policy: SystemExecutionPermissionPolicy | None = None
    blocked_reasons: list[str] = Field(default_factory=list)


class SystemExecutionSession(BaseModel):
    session_id: str
    status: SystemExecutionStatus
    engine: SystemExecutionEngine
    target: SystemExecutionTarget
    dry_run: bool = True
    plan: SystemExecutionPlan
    updated_at: str | None = None
    related_task_id: str | None = None
    related_task_name: str | None = None
    allowed_apps: list[str] = Field(default_factory=list)
    requested_paths: list[str] = Field(default_factory=list)
    requested_commands: list[str] = Field(default_factory=list)
    opened_targets: list[str] = Field(default_factory=list)
    launched_apps: list[str] = Field(default_factory=list)
    executed_commands: list[str] = Field(default_factory=list)
    last_command: str | None = None
    last_exit_code: int | None = None
    last_output: str | None = None
    last_blocked_reason: str | None = None
    pending_step_ids: list[str] = Field(default_factory=list)
    recovery_available: bool = False
    completed_step_ids: list[str] = Field(default_factory=list)


class SystemExecutionCliRequest(BaseModel):
    command: str
    note: str = ""
    require_approval: bool = False
    task_id: str | None = None
    task_name: str | None = None


class SystemExecutionCliResponse(BaseModel):
    session: SystemExecutionSession
    result: SystemExecutionStepExecutionResult


class SystemExecutionSessionListResponse(BaseModel):
    sessions: list[SystemExecutionSession] = Field(default_factory=list)


class SystemExecutionDesktopSnapshot(BaseModel):
    session_id: str
    active_app: str | None = None
    active_window: str | None = None
    focused_target: str | None = None
    screen_summary: str = ""
    cursor_hint: str | None = None
    timestamp: str


class SystemExecutionAuditEntry(BaseModel):
    session_id: str
    step_id: str
    action_kind: SystemExecutionActionKind
    status: Literal["planned", "skipped", "blocked", "simulated", "completed"] = "planned"
    detail: str
    timestamp: str
