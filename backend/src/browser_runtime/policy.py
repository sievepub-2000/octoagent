"""Session policy helpers for browser runtime."""

from __future__ import annotations

from urllib.parse import urlparse

from .contracts import BrowserExecutionSession


def normalize_domain(url: str) -> str | None:
    host = urlparse(url).hostname
    return host.lower() if host else None


class BrowserSessionPolicy:
    """Evaluate domain safety and pending execution state."""

    def is_allowed_target(self, session: BrowserExecutionSession, target: str | None) -> bool:
        if not target:
            return True
        if not session.allowed_domains:
            return True
        domain = normalize_domain(target)
        if domain is None:
            return False
        return any(domain == allowed or domain.endswith(f".{allowed}") for allowed in session.allowed_domains)

    def remaining_action_ids(self, session: BrowserExecutionSession) -> list[str]:
        return [
            action.action_id
            for action in session.planned_actions
            if action.action_id not in session.executed_action_ids
        ]

    def refresh_pending_state(self, session: BrowserExecutionSession) -> None:
        session.pending_action_ids = self.remaining_action_ids(session)
        session.recovery_available = session.status == "failed" and bool(
            session.current_url and session.pending_action_ids
        )
