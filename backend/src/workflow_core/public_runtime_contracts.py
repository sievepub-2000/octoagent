"""Public runtime contracts for external consumption.

These models define the stable, read-first public API surface for workflow
runtime state.  They intentionally project a narrower, more stable view
than the internal studio-runtime contracts so that future Python SDKs,
web widgets and channel integrations do not bind to operator-internal
payloads.

Re-uses ``TaskStudioBindingItem`` and ``TaskStudioBindings`` from the
studio contracts because the binding shape is already clean enough for
public exposure.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Agent summary (public subset of TaskStudioAgentSummary)
# ---------------------------------------------------------------------------

class PublicAgentSummary(BaseModel):
    agent_id: str
    name: str
    role: str
    status: str
    model_name: str | None = None


# ---------------------------------------------------------------------------
# Binding descriptors (re-exported from studio contracts for clarity)
# ---------------------------------------------------------------------------

class PublicBindingItem(BaseModel):
    binding_id: str
    kind: str  # "channel" | "mcp" | "skill" | "plugin"
    label: str
    enabled: bool
    status: str


class PublicBindings(BaseModel):
    channels: list[PublicBindingItem] = Field(default_factory=list)
    mcp_servers: list[PublicBindingItem] = Field(default_factory=list)
    skills: list[PublicBindingItem] = Field(default_factory=list)
    plugins: list[PublicBindingItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Artifact ref (public subset)
# ---------------------------------------------------------------------------

class PublicArtifactRef(BaseModel):
    name: str
    path: str
    download_url: str


# ---------------------------------------------------------------------------
# Timeline event (public subset of TaskStudioTimelineEvent)
# ---------------------------------------------------------------------------

class PublicTimelineEvent(BaseModel):
    event_id: str
    kind: str
    created_at: str
    title: str
    summary: str | None = None


# ---------------------------------------------------------------------------
# Top-level runtime response
# ---------------------------------------------------------------------------

class PublicWorkflowRuntime(BaseModel):
    workflow_id: str
    name: str
    status: str
    phase: str | None = None
    goal: str = ""
    updated_at: str
    agents: list[PublicAgentSummary] = Field(default_factory=list)
    bindings: PublicBindings = Field(default_factory=PublicBindings)
    artifacts: list[PublicArtifactRef] = Field(default_factory=list)
    progress: dict[str, Any] = Field(default_factory=dict)


class PublicWorkflowEvents(BaseModel):
    workflow_id: str
    cursor: int = 0
    next_cursor: int | None = None
    events: list[PublicTimelineEvent] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Binding update request
# ---------------------------------------------------------------------------

class UpdateBindingsRequest(BaseModel):
    channels: list[str] | None = None
    mcp_servers: list[str] | None = None
    skills: list[str] | None = None
    plugins: list[str] | None = None


__all__ = [
    "PublicAgentSummary",
    "PublicArtifactRef",
    "PublicBindingItem",
    "PublicBindings",
    "PublicTimelineEvent",
    "PublicWorkflowEvents",
    "PublicWorkflowRuntime",
    "UpdateBindingsRequest",
    "project_public_runtime",
    "project_public_bindings",
]


# ---------------------------------------------------------------------------
# Pure projection helpers (no heavy deps – safe to test in isolation)
# ---------------------------------------------------------------------------


def project_public_runtime(contract: dict[str, object]) -> dict[str, object]:
    """Transform an internal studio runtime contract into the public shape."""
    agents_raw = contract.get("agents") or []
    agents = [
        {
            "agent_id": a.get("agent_id", ""),
            "name": a.get("name", ""),
            "role": a.get("role", ""),
            "status": a.get("status", "idle"),
            "model_name": a.get("model_name"),
        }
        for a in agents_raw
        if isinstance(a, dict)
    ]
    bindings = project_public_bindings(contract.get("bindings") or {})
    artifacts_raw = contract.get("artifacts") or []
    artifacts = [
        {
            "name": art.get("name", ""),
            "path": art.get("path", ""),
            "download_url": art.get("download_url", ""),
        }
        for art in artifacts_raw
        if isinstance(art, dict)
    ]
    summary = contract.get("runtime_summary") or {}
    progress = contract.get("progress") if isinstance(contract.get("progress"), dict) else None
    if progress is None and isinstance(summary, dict) and summary:
        progress = {
            "completed_count": summary.get("completed_count", 0),
            "total_count": summary.get("total_count", 0),
            "pct": summary.get("pct", 0),
        }
    phase = contract.get("phase")
    if not phase and isinstance(summary, dict):
        phase = summary.get("current_phase")
    return {
        "workflow_id": contract.get("task_id", ""),
        "name": contract.get("name", ""),
        "status": contract.get("status", "unknown"),
        "phase": phase or "unknown",
        "goal": contract.get("goal"),
        "updated_at": contract.get("updated_at"),
        "agents": agents,
        "bindings": bindings,
        "artifacts": artifacts,
        "progress": progress,
    }


def project_public_bindings(bindings: dict[str, object]) -> dict[str, object]:
    """Project studio bindings into the narrower public shape."""
    def _project_items(items: list[object]) -> list[dict[str, str | bool]]:
        return [
            {
                "binding_id": item.get("binding_id", item.get("name", "")),
                "kind": item.get("kind", ""),
                "label": item.get("label", item.get("name", "")),
                "enabled": item.get("enabled", True),
                "status": item.get("status", "unknown"),
            }
            for item in items
            if isinstance(item, dict)
        ]
    return {
        "channels": _project_items(bindings.get("channels") or []),
        "mcp_servers": _project_items(bindings.get("mcp_servers") or []),
        "skills": _project_items(bindings.get("skills") or []),
        "plugins": _project_items(bindings.get("plugins") or []),
    }
