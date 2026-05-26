"""Contract-first service facade for browser runtime providers."""

from __future__ import annotations

from datetime import UTC, datetime
from src.utils.datetime import utc_now_iso as _utc_now

from .contracts import (
    BrowserActionContract,
    BrowserActionExecutionRequest,
    BrowserActionExecutionResult,
    BrowserExecutionSession,
    BrowserProviderProfile,
    BrowserRuntimeCapability,
    BrowserRuntimeStatusSnapshot,
    BrowserSessionEvent,
    BrowserSessionRecoveryRequest,
    BrowserSessionRequest,
    BrowserSessionUpdateRequest,
)
from .execution import BrowserSessionExecutionEngine
from .policy import BrowserSessionPolicy
from .profiles import BrowserRuntimeProfileCatalog
from .store import BrowserRuntimeStore




class BrowserRuntimeService:
    """Facade over browser runtime profiles, policy, execution, and storage."""

    def __init__(self):
        self._store = BrowserRuntimeStore()
        self._profiles = BrowserRuntimeProfileCatalog()
        self._policy = BrowserSessionPolicy()
        self._execution = BrowserSessionExecutionEngine(policy=self._policy)
        self._sessions: dict[str, BrowserExecutionSession] = {}
        persisted = self._store.list_sessions()
        for session in persisted or self._seed_sessions():
            self._policy.refresh_pending_state(session)
            self._sessions[session.session_id] = session
        if not persisted:
            self._persist_sessions()

    def get_capability(self) -> BrowserRuntimeCapability:
        return self._profiles.get_capability()

    def list_provider_profiles(self) -> list[BrowserProviderProfile]:
        return self._profiles.list_provider_profiles()

    def _fetch_page(self, target: str) -> dict[str, str | int | list[str] | None]:
        return self._execution.fetch_page(target)

    def _persist_sessions(self) -> None:
        self._store.save_sessions(list(self._sessions.values()))

    def _seed_sessions(self) -> list[BrowserExecutionSession]:
        timestamp = _utc_now()
        return [
            BrowserExecutionSession(
                session_id="browser-session-seed",
                provider="agent_browser",
                target="https://example.com",
                status="planned",
                allowed_domains=["example.com"],
                requires_approval=True,
                planned_actions=[
                    BrowserActionContract(
                        action_id="browser-action-open-seed",
                        kind="open",
                        target="https://example.com",
                        requires_approval=True,
                    ),
                    BrowserActionContract(
                        action_id="browser-action-snapshot-seed",
                        kind="snapshot",
                        requires_approval=False,
                    ),
                ],
                session_type="ephemeral",
                policy_label="approval_required",
                created_at=timestamp,
                updated_at=timestamp,
                current_url="https://example.com",
                pending_action_ids=[
                    "browser-action-open-seed",
                    "browser-action-snapshot-seed",
                ],
                events=[
                    BrowserSessionEvent(
                        event_id="browser-event-browser-session-seed-1",
                        session_id="browser-session-seed",
                        kind="created",
                        detail="Seed browser session created for capability discovery.",
                        created_at=timestamp,
                    )
                ],
            )
        ]

    def list_sessions(self) -> list[BrowserExecutionSession]:
        return sorted(self._sessions.values(), key=lambda item: item.created_at or "", reverse=True)

    def get_session(self, session_id: str) -> BrowserExecutionSession | None:
        return self._sessions.get(session_id)

    def get_status_snapshot(self) -> BrowserRuntimeStatusSnapshot:
        sessions = self.list_sessions()
        return BrowserRuntimeStatusSnapshot(
            total_sessions=len(sessions),
            planned_sessions=sum(1 for session in sessions if session.status == "planned"),
            running_sessions=sum(1 for session in sessions if session.status == "running"),
            completed_sessions=sum(1 for session in sessions if session.status == "completed"),
            failed_sessions=sum(1 for session in sessions if session.status == "failed"),
            recoverable_sessions=sum(1 for session in sessions if session.recovery_available),
            recent_session_ids=[session.session_id for session in sessions[:5]],
            active_provider_ids=sorted({session.provider for session in sessions}),
        )

    def create_session(
        self,
        request: BrowserSessionRequest,
        *,
        created_at: str | None = None,
    ) -> BrowserExecutionSession:
        timestamp = created_at or _utc_now()
        planned_actions = list(request.actions)
        if not planned_actions:
            planned_actions = [
                BrowserActionContract(
                    action_id=f"browser-action-open-{len(self._sessions) + 1}",
                    kind="open",
                    target=request.target,
                    requires_approval=request.requires_approval,
                ),
                BrowserActionContract(
                    action_id=f"browser-action-snapshot-{len(self._sessions) + 1}",
                    kind="snapshot",
                    requires_approval=False,
                ),
            ]
        session_id = f"browser-session-{len(self._sessions) + 1}"
        session = BrowserExecutionSession(
            session_id=session_id,
            provider=request.provider,
            target=request.target,
            status="planned",
            allowed_domains=request.allowed_domains,
            requires_approval=request.requires_approval,
            planned_actions=planned_actions,
            session_type=request.session_type,
            policy_label=request.policy_label,
            created_at=timestamp,
            updated_at=timestamp,
            current_url=request.target,
            available_targets=[],
            available_inputs=[],
            form_state={},
            pending_action_ids=[action.action_id for action in planned_actions],
            recovery_available=False,
            executed_action_ids=[],
            events=[
                BrowserSessionEvent(
                    event_id=f"browser-event-{session_id}-1",
                    session_id=session_id,
                    kind="created",
                    detail="Browser session created from runtime request.",
                    created_at=timestamp,
                )
            ],
        )
        self._policy.refresh_pending_state(session)
        self._sessions[session.session_id] = session
        self._persist_sessions()
        return session

    def execute_next_action(
        self,
        session_id: str,
        request: BrowserActionExecutionRequest,
        *,
        executed_at: str | None = None,
    ) -> BrowserActionExecutionResult | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        result = self._execution.execute_next_action(
            session,
            request,
            executed_at=executed_at or _utc_now(),
            fetch_page=self._fetch_page,
        )
        self._persist_sessions()
        return result

    def recover_session(
        self,
        session_id: str,
        request: BrowserSessionRecoveryRequest,
        *,
        recovered_at: str | None = None,
    ) -> BrowserExecutionSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        updated = self._execution.recover_session(
            session,
            request,
            recovered_at=recovered_at or _utc_now(),
        )
        self._persist_sessions()
        return updated

    def update_session(
        self,
        session_id: str,
        request: BrowserSessionUpdateRequest,
        *,
        updated_at: str | None = None,
    ) -> BrowserExecutionSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        updated = self._execution.update_session(
            session,
            request,
            updated_at=updated_at or _utc_now(),
        )
        self._persist_sessions()
        return updated


_service = BrowserRuntimeService()


def get_browser_runtime_service() -> BrowserRuntimeService:
    return _service
