"""Session governance helpers for client/server operation coordination."""

from __future__ import annotations

import re

from .contracts import (
    QueryClientCommand,
    QueryGoalDriftReport,
    QueryMemoryProfile,
    QuerySessionGovernance,
)

_TOKEN_RE = re.compile(r"[\w\-]{2,}", re.UNICODE)
_DRIFT_HINTS = (
    "instead",
    "switch",
    "different",
    "new task",
    "change direction",
    "改成",
    "换成",
    "不要",
    "改为",
)


def _tokenize(value: str | None) -> set[str]:
    if not value:
        return set()
    return {token.lower() for token in _TOKEN_RE.findall(value)}


def build_goal_drift_report(current_goal: str | None, user_message: str) -> QueryGoalDriftReport:
    goal_tokens = _tokenize(current_goal)
    message_tokens = _tokenize(user_message)
    if not goal_tokens or not message_tokens:
        return QueryGoalDriftReport()

    overlap = goal_tokens & message_tokens
    score = round(len(overlap) / max(1, len(goal_tokens)), 2)
    lowered_message = user_message.lower()
    drift_hint = any(marker in lowered_message for marker in _DRIFT_HINTS)

    if score >= 0.45 and not drift_hint:
        return QueryGoalDriftReport(
            status="aligned",
            score=score,
            reason="Current turn still overlaps strongly with the active goal.",
        )
    if score >= 0.2 and not drift_hint:
        return QueryGoalDriftReport(
            status="watch",
            score=score,
            reason="Current turn only partially overlaps with the active goal and should be monitored.",
            suggested_focus=current_goal,
        )
    return QueryGoalDriftReport(
        status="drifting",
        score=score,
        reason="Current turn appears to be changing direction relative to the active goal.",
        suggested_focus=current_goal,
    )


def build_session_governance(
    *,
    current_goal: str | None,
    user_message: str,
    memory_profile: QueryMemoryProfile | None,
    active_operation: QueryClientCommand,
    continuation_source: str | None = None,
    previous_session_id: str | None = None,
    archived_turn_count: int = 0,
) -> QuerySessionGovernance:
    if continuation_source:
        continuation_mode = "resumed"
        continuity_summary = f"Resuming prior work from '{continuation_source}'."
    elif previous_session_id:
        continuation_mode = "continued"
        continuity_summary = f"Session inherits prior context from '{previous_session_id}'."
    else:
        continuation_mode = "fresh"
        continuity_summary = "Fresh session with no prior handoff detected."

    if memory_profile is None:
        context_pressure = "medium" if archived_turn_count >= 4 else "low"
        recommended_memory_action = "refresh" if archived_turn_count >= 4 else "continue"
    else:
        context_pressure = memory_profile.context_pressure
        recommended_memory_action = memory_profile.recommended_action

    return QuerySessionGovernance(
        continuation_mode=continuation_mode,
        continuity_summary=continuity_summary,
        context_pressure=context_pressure,
        recommended_memory_action=recommended_memory_action,
        goal_drift=build_goal_drift_report(current_goal, user_message),
        active_operation=active_operation,
    )
