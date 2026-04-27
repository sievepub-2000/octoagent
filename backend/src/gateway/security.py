"""Shared FastAPI security helpers for operator and worker guarded routes."""

from __future__ import annotations

from fastapi import HTTPException

from src.operator_governance import require_operator_access, token_matches_env


def require_operator_or_403(
    *,
    role: str | None,
    token: str | None,
    minimum: str = "operator",
    token_env: str = "OCTO_OPERATOR_TOKEN",
) -> None:
    """Translate shared operator governance checks into gateway HTTP errors."""
    try:
        require_operator_access(role=role, token=token, minimum=minimum, token_env=token_env)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def require_worker_token_or_403(
    provided: str | None,
    *,
    token_env: str = "OCTO_EXECUTION_WORKER_TOKEN",
) -> None:
    """Require the configured worker token when production enables one."""
    if not token_matches_env(token_env, provided):
        raise HTTPException(status_code=403, detail="Invalid execution worker token")
