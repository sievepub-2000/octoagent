"""Versioned, deterministic state contract for context rollover."""

from __future__ import annotations

import hashlib
import json
from typing import Any

CONTINUATION_CONTRACT_VERSION = 2

_LIST_FIELDS = (
    "constraints",
    "forbidden_actions",
    "acceptance_criteria",
    "confirmed_decisions",
    "completed_steps",
    "pending_steps",
    "blockers",
    "evidence",
    "artifacts",
)


def _text(value: Any, limit: int = 1_200) -> str:
    text = " ".join(str(value or "").strip().split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _items(value: Any, *, limit: int = 16, item_limit: int = 600) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = _text(raw, item_limit)
        key = item.casefold()
        if not item or key in seen:
            continue
        result.append(item)
        seen.add(key)
        if len(result) >= limit:
            break
    return result


def _pending_todos(context: dict[str, Any]) -> list[str]:
    todos = context.get("continue_todos") or []
    if not isinstance(todos, list):
        return []
    return _items([todo.get("content") for todo in todos if isinstance(todo, dict) and str(todo.get("status") or "").strip().lower() in {"pending", "in_progress", "active", "running"}])


def normalize_continuation_contract(context: dict[str, Any]) -> dict[str, Any] | None:
    """Return the single authoritative rollover contract, adapting legacy state."""
    raw = context.get("continue_contract")
    raw = dict(raw) if isinstance(raw, dict) else {}
    task_state = context.get("continue_task_state")
    task_state = dict(task_state) if isinstance(task_state, dict) else {}

    objective = _text(raw.get("objective") or task_state.get("goal"))
    if not objective:
        return None

    contract: dict[str, Any] = {
        "version": CONTINUATION_CONTRACT_VERSION,
        "objective": objective,
        "status": _text(raw.get("status") or task_state.get("status") or "active", 40),
        "current_phase": _text(raw.get("current_phase") or task_state.get("current_step"), 800),
        "next_action": _text(raw.get("next_action") or task_state.get("next_action"), 800),
        "permission_scope": _text(raw.get("permission_scope") or task_state.get("permission_scope"), 500),
        "source_thread_id": _text(raw.get("source_thread_id") or context.get("continue_from_thread_id"), 200),
        "source_title": _text(raw.get("source_title") or context.get("continue_from_title"), 300),
    }
    for field in _LIST_FIELDS:
        contract[field] = _items(raw.get(field) or task_state.get(field))

    contract["pending_steps"] = _items([*contract["pending_steps"], *_pending_todos(context)])
    if not contract["next_action"] and contract["pending_steps"]:
        contract["next_action"] = contract["pending_steps"][0]

    hash_payload = {key: value for key, value in contract.items() if key != "contract_hash"}
    contract["contract_hash"] = hashlib.sha256(json.dumps(hash_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:20]
    return contract


def contract_to_task_state(contract: dict[str, Any]) -> dict[str, Any]:
    """Adapt the v2 contract to the existing persistent task-state Interface."""
    return {
        "version": CONTINUATION_CONTRACT_VERSION,
        "goal": contract["objective"],
        "status": contract.get("status") or "active",
        "current_step": contract.get("current_phase") or contract.get("next_action") or "resume work",
        "completed_steps": list(contract.get("completed_steps") or []),
        "pending_steps": list(contract.get("pending_steps") or []),
        "evidence": list(contract.get("evidence") or []),
        "failed_attempts": [],
        "next_action": contract.get("next_action") or "",
        "constraints": list(contract.get("constraints") or []),
        "forbidden_actions": list(contract.get("forbidden_actions") or []),
        "acceptance_criteria": list(contract.get("acceptance_criteria") or []),
        "confirmed_decisions": list(contract.get("confirmed_decisions") or []),
        "blockers": list(contract.get("blockers") or []),
        "artifacts": list(contract.get("artifacts") or []),
        "permission_scope": contract.get("permission_scope") or "",
        "continuation_contract_hash": contract.get("contract_hash") or "",
    }


def render_active_contract(contract: dict[str, Any]) -> str:
    """Render compact model context without mixing active work with history."""
    lines = [
        "Authoritative active contract:",
        f"- Objective: {contract['objective']}",
        f"- Status: {contract.get('status') or 'active'}",
    ]
    for label, key in (("Current phase", "current_phase"), ("Next action", "next_action"), ("Permission scope", "permission_scope")):
        if contract.get(key):
            lines.append(f"- {label}: {contract[key]}")
    for label, key in (
        ("Constraints", "constraints"),
        ("Forbidden actions", "forbidden_actions"),
        ("Acceptance criteria", "acceptance_criteria"),
        ("Confirmed decisions", "confirmed_decisions"),
        ("Completed steps — do not repeat", "completed_steps"),
        ("Pending steps", "pending_steps"),
        ("Blockers", "blockers"),
        ("Evidence", "evidence"),
        ("Artifacts", "artifacts"),
    ):
        values = contract.get(key) or []
        if values:
            lines.append(f"- {label}:")
            lines.extend(f"  - {item}" for item in values)
    lines.append(f"- Contract hash: {contract.get('contract_hash') or 'legacy'}")
    return "\n".join(lines)
