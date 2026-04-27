"""Shared task-scoped agent session helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.query_engine import QuerySession


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def find_task_agent(workspace: Any, agent_id: str):
    if workspace is None:
        return None
    return next((agent for agent in workspace.agents if agent.agent_id == agent_id), None)


def resolve_query_session_id(
    workspace: Any,
    agent_id: str,
    *,
    query_service=None,
) -> str | None:
    candidate_ids: list[str] = []
    agent = find_task_agent(workspace, agent_id)
    if agent is not None:
        session_id = str(agent.metadata.get("query_session_id") or "").strip()
        if session_id:
            candidate_ids.append(session_id)
    if workspace is not None:
        session_id = str(workspace.metadata.get("last_handoff_session_id") or "").strip()
        if session_id and session_id not in candidate_ids:
            candidate_ids.append(session_id)
    for session_id in candidate_ids:
        if query_service is None or query_service.get_session(session_id) is not None:
            return session_id
    return None


def mark_query_session_running(
    query_session_id: str | None,
    *,
    user_message: str,
    created_at: str,
    query_service=None,
) -> QuerySession | None:
    """Mark an existing query session as actively running."""
    if not query_session_id:
        return None
    if query_service is None:
        from src.query_engine import get_query_engine_service

        query_service = get_query_engine_service()
    return query_service.mark_session_running(
        query_session_id,
        user_message=user_message,
        created_at=created_at,
    )


def record_query_agent_execution(
    query_session_id: str | None,
    *,
    user_message: str,
    assistant_summary: str,
    tool_call_count: int,
    execution_target: str | None,
    execution_status: str,
    runtime_provider: str | None,
    runtime_session_id: str | None,
    runtime_step_id: str | None,
    created_at: str,
    query_service=None,
) -> QuerySession | None:
    """Persist a task-scoped agent execution back into QueryEngine."""
    if not query_session_id:
        return None
    if query_service is None:
        from src.query_engine import get_query_engine_service

        query_service = get_query_engine_service()
    return query_service.record_agent_execution(
        query_session_id,
        user_message=user_message,
        assistant_summary=assistant_summary,
        tool_call_count=tool_call_count,
        execution_target=execution_target,
        execution_status=execution_status,
        runtime_provider=runtime_provider,
        runtime_session_id=runtime_session_id,
        runtime_step_id=runtime_step_id,
        created_at=created_at,
    )


def find_linked_card_for_agent(workspace: Any, agent: Any):
    linked_cards = [card for card in workspace.card_graph.cards if card.linked_agent_id == agent.agent_id]
    linked_card = next((card for card in linked_cards if card.card_id == agent.linked_card_id), None)
    if linked_card is not None:
        return linked_card
    return linked_cards[0] if linked_cards else None


def build_agent_session_updates(session: QuerySession) -> dict[str, object]:
    updates: dict[str, object] = {
        "query_session_id": session.session_id,
        "query_session_status": session.status,
        "last_session_updated_at": session.updated_at,
    }
    latest_turn = session.turns[-1] if session.turns else None
    if latest_turn is not None:
        updates.update(
            {
                "last_turn_id": latest_turn.turn_id,
                "last_turn_summary": latest_turn.assistant_summary,
                "last_execution_target": latest_turn.execution_target,
                "last_execution_status": latest_turn.execution_status,
                "last_runtime_provider": latest_turn.runtime_provider,
                "runtime_session_id": latest_turn.runtime_session_id,
                "runtime_step_id": latest_turn.runtime_step_id,
            }
        )
    return updates


def build_workspace_session_updates(workspace: Any, latest_session: QuerySession) -> dict[str, object]:
    updates: dict[str, object] = {
        "last_handoff_session_id": latest_session.session_id,
        "last_runtime_sync_at": _utc_now(),
        "active_query_session_count": sum(
            1 for agent in workspace.agents if agent.metadata.get("query_session_id")
        ),
    }
    latest_turn = latest_session.turns[-1] if latest_session.turns else None
    if latest_turn is not None:
        updates.update(
            {
                "last_execution_target": latest_turn.execution_target,
                "last_execution_status": latest_turn.execution_status,
                "last_runtime_provider": latest_turn.runtime_provider,
                "last_runtime_session_id": latest_turn.runtime_session_id,
                "last_runtime_step_id": latest_turn.runtime_step_id,
                "last_agent_result_summary": latest_turn.assistant_summary,
            }
        )
    return updates


def build_card_runtime_state(session: QuerySession) -> dict[str, object]:
    latest_turn = session.turns[-1] if session.turns else None
    return {
        "query_session_id": session.session_id,
        "query_session_status": session.status,
        "last_execution_target": latest_turn.execution_target if latest_turn is not None else None,
        "last_execution_status": latest_turn.execution_status if latest_turn is not None else None,
        "last_runtime_provider": latest_turn.runtime_provider if latest_turn is not None else None,
        "runtime_session_id": latest_turn.runtime_session_id if latest_turn is not None else None,
        "runtime_step_id": latest_turn.runtime_step_id if latest_turn is not None else None,
    }


def sync_workspace_session_state(workspace: Any, *, query_service) -> bool:
    """Project query-session truth back into workspace agent/card state."""
    from src.workflow_core.status import (
        agent_status_from_query_session,
        agent_status_from_workspace_terminal_state,
    )

    changed = False
    latest_session: QuerySession | None = None
    for agent in workspace.agents:
        session = query_service.latest_session_for_agent(
            workspace.task_id, agent.agent_id
        )
        if session is None:
            continue
        if latest_session is None or session.updated_at >= latest_session.updated_at:
            latest_session = session
        latest_turn = session.turns[-1] if session.turns else None
        next_agent_status = agent_status_from_query_session(
            session.status,
            latest_turn.execution_status if latest_turn is not None else None,
        )
        next_agent_status = agent_status_from_workspace_terminal_state(
            workspace.status,
            agent.status,
            next_agent_status,
        )
        if agent.status != next_agent_status:
            agent.status = next_agent_status  # type: ignore[assignment]
            changed = True
        agent_updates = build_agent_session_updates(session)
        if any(agent.metadata.get(key) != value for key, value in agent_updates.items()):
            agent.metadata.update(agent_updates)
            changed = True
        if _sync_linked_card_runtime_state(workspace, agent, session):
            changed = True

    if latest_session is not None:
        workspace_updates = build_workspace_session_updates(workspace, latest_session)
        if any(
            workspace.metadata.get(key) != value
            for key, value in workspace_updates.items()
        ):
            workspace.metadata.update(workspace_updates)
            changed = True
    return changed


def build_agent_runtime_summary(
    workspace: Any,
    query_sessions: list[QuerySession],
) -> list[dict[str, object]]:
    """Build a compact agent runtime summary for studio runtime contracts.

    Centralizes the per-agent snapshot that was previously assembled inline
    in ``WorkflowCoreService.get_studio_runtime_contract()``.
    """
    items: list[dict[str, object]] = []
    for agent in workspace.agents:
        agent_metadata = agent.metadata or {}
        items.append(
            {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "role": agent.role,
                "status": agent.status,
                "model_name": agent.model_name,
                "task_scope": agent.task_scope,
                "linked_card_id": agent.linked_card_id,
                "query_session_id": _safe_str(agent_metadata, "query_session_id"),
                "runtime_session_id": _safe_str(agent_metadata, "runtime_session_id"),
                "langgraph_assistant_id": _safe_str(agent_metadata, "langgraph_assistant_id"),
                "langgraph_thread_scope": _safe_str(agent_metadata, "langgraph_thread_scope"),
                "last_runtime_provider": _safe_str(agent_metadata, "last_runtime_provider"),
                "last_execution_target": _safe_str(agent_metadata, "last_execution_target"),
                "last_execution_status": _safe_str(agent_metadata, "last_execution_status"),
                "last_result_summary": _safe_str(agent_metadata, "last_agent_result_summary"),
                "message_count": agent.conversation.message_count,
                "last_message_at": agent.conversation.last_message_at,
            }
        )
    return items


def build_handoff_summary(
    workspace: Any,
    query_sessions: list[QuerySession],
) -> list[dict[str, object]]:
    """Build a compact handoff summary for studio runtime contracts.

    Centralizes the handoff assembly that was previously inline in the
    studio runtime contract builder.
    """
    agents = list(workspace.agents)
    management_agent = next(
        (
            agent
            for agent in agents
            if agent.role in {"lead", "coordinator", "manager", "orchestrator"}
        ),
        agents[0] if agents else None,
    )
    handoffs: list[dict[str, object]] = []
    for session in sorted(query_sessions, key=lambda s: s.created_at, reverse=True):
        if management_agent is None or session.agent_id == management_agent.agent_id:
            continue
        target_agent = next(
            (a for a in agents if a.agent_id == session.agent_id), None
        )
        target_metadata = (
            target_agent.metadata
            if target_agent is not None and isinstance(target_agent.metadata, dict)
            else {}
        )
        latest_turn = session.turns[-1] if session.turns else None
        handoffs.append(
            {
                "handoff_id": f"handoff-{session.session_id}",
                "source_agent_id": management_agent.agent_id,
                "target_agent_id": session.agent_id,
                "status": session.status,
                "query_session_id": session.session_id,
                "runtime_session_id": _safe_str(target_metadata, "runtime_session_id"),
                "linked_card_id": (
                    target_agent.linked_card_id if target_agent is not None else None
                ),
                "created_at": session.created_at,
                "summary": (
                    latest_turn.assistant_summary if latest_turn is not None else None
                ),
            }
        )
    return handoffs


def _sync_linked_card_runtime_state(
    workspace: Any,
    agent: Any,
    session: QuerySession,
) -> bool:
    from src.workflow_core.status import (
        TERMINAL_WORKSPACE_STATUSES,
        card_status_from_agent_status,
        card_status_from_query_session,
    )

    linked_card = find_linked_card_for_agent(workspace, agent)
    if linked_card is None:
        return False
    latest_turn = session.turns[-1] if session.turns else None
    if workspace.status in TERMINAL_WORKSPACE_STATUSES:
        next_card_status = card_status_from_agent_status(agent.status)
    else:
        next_card_status = card_status_from_query_session(
            session.status,
            latest_turn.execution_status if latest_turn is not None else None,
        )
    changed = False
    if linked_card.status != next_card_status:
        linked_card.status = next_card_status  # type: ignore[assignment]
        changed = True
    card_runtime = build_card_runtime_state(session)
    current_runtime = dict(linked_card.config.get("runtime_state", {}))
    if current_runtime != card_runtime:
        linked_card.config["runtime_state"] = card_runtime
        changed = True
    return changed


def _safe_str(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


__all__ = [
    "build_agent_runtime_summary",
    "build_agent_session_updates",
    "build_card_runtime_state",
    "build_handoff_summary",
    "build_workspace_session_updates",
    "find_linked_card_for_agent",
    "find_task_agent",
    "mark_query_session_running",
    "record_query_agent_execution",
    "resolve_query_session_id",
    "sync_workspace_session_state",
]