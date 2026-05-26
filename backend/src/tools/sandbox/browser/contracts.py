"""Contracts for browser runtime providers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BrowserProviderProfile(BaseModel):
    provider_id: str
    display_name: str
    launch_mode: Literal["cli", "service", "remote"] = "cli"
    default_session_type: Literal["ephemeral", "persistent"] = "ephemeral"
    supports_accessibility_snapshot: bool = True
    supports_batch_commands: bool = False
    supports_streaming: bool = False
    recommended_for_default_use: bool = False


class BrowserActionContract(BaseModel):
    action_id: str
    kind: Literal["open", "snapshot", "click", "fill", "eval", "screenshot", "wait"]
    target: str | None = None
    value: str | None = None
    requires_approval: bool = False


class BrowserRuntimeCapability(BaseModel):
    enabled: bool = True
    default_provider: Literal["agent_browser", "none"] = "agent_browser"
    supports_cloud_sandbox: bool = True
    supports_authenticated_sessions: bool = False
    embedded_engine: str = "playwright"
    executable_path: str | None = None
    supports_high_privilege_mode: bool = False
    supports_policy_profiles: bool = True
    note: str = "Browser runtime uses the configured embedded headless provider for browser-scoped actions and falls back to HTTP fetch only when the provider is unavailable."


class BrowserRuntimeStatusSnapshot(BaseModel):
    total_sessions: int = 0
    planned_sessions: int = 0
    running_sessions: int = 0
    completed_sessions: int = 0
    failed_sessions: int = 0
    recoverable_sessions: int = 0
    recent_session_ids: list[str] = Field(default_factory=list)
    active_provider_ids: list[str] = Field(default_factory=list)


class BrowserSessionRequest(BaseModel):
    target: str
    allowed_domains: list[str] = Field(default_factory=list)
    provider: str = "agent_browser"
    requires_approval: bool = True
    session_type: Literal["ephemeral", "persistent"] = "ephemeral"
    actions: list[BrowserActionContract] = Field(default_factory=list)
    policy_label: Literal["safe_read", "approval_required", "high_privilege"] = "approval_required"


class BrowserSessionEvent(BaseModel):
    event_id: str
    session_id: str
    kind: Literal["created", "started", "completed", "failed", "note"]
    detail: str
    created_at: str


class BrowserSessionUpdateRequest(BaseModel):
    status: Literal["running", "completed", "failed"]
    detail: str = ""


class BrowserSessionRecoveryRequest(BaseModel):
    note: str = ""


class BrowserActionExecutionRequest(BaseModel):
    note: str = ""


class BrowserActionExecutionResult(BaseModel):
    session_id: str
    action_id: str
    status: Literal["simulated", "blocked", "completed"] = "simulated"
    detail: str
    remaining_actions: int
    current_url: str | None = None
    page_title: str | None = None
    snapshot_summary: str | None = None
    available_target_count: int = 0
    available_input_count: int = 0
    recovery_available: bool = False
    artifact_path: str | None = None


class BrowserExecutionSession(BaseModel):
    session_id: str
    provider: str
    target: str
    status: Literal["planned", "running", "completed", "failed"] = "planned"
    allowed_domains: list[str] = Field(default_factory=list)
    requires_approval: bool = True
    planned_actions: list[BrowserActionContract] = Field(default_factory=list)
    session_type: Literal["ephemeral", "persistent"] = "ephemeral"
    policy_label: Literal["safe_read", "approval_required", "high_privilege"] = "approval_required"
    created_at: str | None = None
    updated_at: str | None = None
    current_url: str | None = None
    page_title: str | None = None
    available_targets: list[str] = Field(default_factory=list)
    available_inputs: list[str] = Field(default_factory=list)
    form_state: dict[str, str] = Field(default_factory=dict)
    last_action_id: str | None = None
    last_action_detail: str | None = None
    last_action_status: Literal["simulated", "blocked", "completed"] | None = None
    latest_snapshot_summary: str | None = None
    latest_artifact_path: str | None = None
    last_fetch_status_code: int | None = None
    last_failure_detail: str | None = None
    pending_action_ids: list[str] = Field(default_factory=list)
    recovery_available: bool = False
    executed_action_ids: list[str] = Field(default_factory=list)
    events: list[BrowserSessionEvent] = Field(default_factory=list)
