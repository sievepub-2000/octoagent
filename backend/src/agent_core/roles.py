"""Shared task-scoped agent role resolution helpers."""

from __future__ import annotations

from typing import Any


def is_management_role(role: str | None) -> bool:
    return role in {"lead", "coordinator", "manager"}


def is_reviewer_role(role: str | None) -> bool:
    return role == "reviewer"


def select_lead_agent(agents: list[Any]):
    lead_agent = next(
        (agent for agent in agents if is_management_role(getattr(agent, "role", None))),
        None,
    )
    if lead_agent is not None:
        return lead_agent
    return agents[0] if agents else None


def select_reviewer_agent(agents: list[Any], *, exclude_agent_id: str | None = None):
    return next(
        (
            agent
            for agent in agents
            if is_reviewer_role(getattr(agent, "role", None))
            and (exclude_agent_id is None or getattr(agent, "agent_id", None) != exclude_agent_id)
        ),
        None,
    )


def split_execution_roles(workspace) -> tuple[Any, list[Any], Any | None]:
    agents = list(getattr(workspace, "agents", []) or [])
    lead_agent = select_lead_agent(agents)
    if lead_agent is None:
        task_id = getattr(workspace, "task_id", "unknown-task")
        raise ValueError(f"Task workspace '{task_id}' has no agents")
    review_agent = select_reviewer_agent(agents, exclude_agent_id=getattr(lead_agent, "agent_id", None))
    worker_agents = [
        agent
        for agent in agents
        if getattr(agent, "agent_id", None) != getattr(lead_agent, "agent_id", None)
        and (review_agent is None or getattr(agent, "agent_id", None) != getattr(review_agent, "agent_id", None))
    ]
    return lead_agent, worker_agents, review_agent


def has_reviewer_agent(agents: list[Any]) -> bool:
    return select_reviewer_agent(agents) is not None


__all__ = [
    "has_reviewer_agent",
    "is_management_role",
    "is_reviewer_role",
    "select_lead_agent",
    "select_reviewer_agent",
    "split_execution_roles",
]