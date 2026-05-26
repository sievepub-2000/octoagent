"""Normalized studio runtime contract builder.

Provides a single ``build_studio_runtime_contract`` factory that can be
consumed by the gateway studio-runtime endpoint, the public API projection,
and future webhook / SSE surfaces.  Keeps the heavy assembly logic out of
``WorkflowCoreService`` while maintaining a stable contract shape.

This module is intentionally side-effect-free and does not import gateway
or FastAPI dependencies.
"""

from __future__ import annotations

from typing import Any


def build_normalized_runtime(
    raw_contract: dict[str, Any],
) -> dict[str, Any]:
    """Return a stable normalized snapshot from the raw studio contract.

    The normalized form is a strict subset of ``TaskStudioRuntimeResponse``
    with additional computed summary fields useful for both frontend panels
    and webhook payloads.

    Keys added / derived:
      - ``health``: one of ``healthy | degraded | unhealthy``
      - ``agent_summary``: short overview string for notifications
      - ``binding_summary``: compact binding count string
    """
    agents: list[dict[str, Any]] = raw_contract.get("agents") or []
    workflow_summary: dict[str, Any] = raw_contract.get("workflow_summary") or {}
    runtime_summary: dict[str, Any] = raw_contract.get("runtime_summary") or {}

    # Compute health
    status = raw_contract.get("status", "unknown")
    blocked = workflow_summary.get("blocked_cards", 0)
    failed_agents = sum(1 for agent in agents if agent.get("status") == "failed")
    if status in ("failed",) or failed_agents > 0:
        health = "unhealthy"
    elif status in ("paused", "waiting_review") or blocked > 0:
        health = "degraded"
    else:
        health = "healthy"

    # Agent summary text
    active = sum(1 for agent in agents if agent.get("status") in ("running", "waiting_handoff"))
    agent_summary = f"{len(agents)} agents ({active} active, {failed_agents} failed)"

    # Binding summary
    bindings: dict[str, Any] = raw_contract.get("bindings") or {}
    binding_counts = {key: len(items) for key, items in bindings.items() if isinstance(items, list)}
    binding_summary = " · ".join(f"{k}={v}" for k, v in sorted(binding_counts.items()) if v)

    return {
        **raw_contract,
        "health": health,
        "agent_summary": agent_summary,
        "binding_summary": binding_summary or "no bindings",
        "phase": runtime_summary.get("current_phase", "idle"),
    }


__all__ = ["build_normalized_runtime"]
