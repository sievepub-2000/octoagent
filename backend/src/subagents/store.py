"""Thread-safe in-memory state store for subagent jobs."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime
from threading import Condition, Lock

from .contracts import SubagentEvent, SubagentResult, SubagentStatus


class SubagentJobStore:
    """In-memory store with condition-based wakeups for delegated jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, SubagentResult] = {}
        self._events: dict[str, deque[SubagentEvent]] = {}
        self._terminal_signals: dict[str, Condition] = {}
        self._cancel_requested: set[str] = set()
        self._lock = Lock()

    def create(self, result: SubagentResult) -> None:
        with self._lock:
            self._jobs[result.task_id] = deepcopy(result)
            self._events[result.task_id] = deque()
            self._terminal_signals[result.task_id] = Condition(self._lock)

    def exists(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._jobs

    def get(self, job_id: str) -> SubagentResult | None:
        with self._lock:
            result = self._jobs.get(job_id)
            return deepcopy(result) if result is not None else None

    def list(self) -> list[SubagentResult]:
        with self._lock:
            return [deepcopy(item) for item in self._jobs.values()]

    def request_cancel(self, job_id: str) -> bool:
        with self._lock:
            if job_id not in self._jobs:
                return False
            self._cancel_requested.add(job_id)
            result = self._jobs[job_id]
            result.cancellation_requested_at = datetime.now()
            if not result.status.is_terminal:
                result.status = SubagentStatus.CANCEL_REQUESTED
                result.updated_at = datetime.now()
                self._terminal_signals[job_id].notify_all()
            return True

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancel_requested

    def append_event(self, event: SubagentEvent) -> None:
        with self._lock:
            events = self._events.get(event.job_id)
            result = self._jobs.get(event.job_id)
            if events is None or result is None:
                return
            events.append(deepcopy(event))
            result.event_count += 1
            result.updated_at = datetime.now()
            if event.status.is_terminal:
                self._terminal_signals[event.job_id].notify_all()

    def pop_events(self, job_id: str) -> list[SubagentEvent]:
        with self._lock:
            events = self._events.get(job_id)
            if events is None:
                return []
            popped = list(events)
            events.clear()
            return popped

    def update(
        self,
        job_id: str,
        *,
        status: SubagentStatus | None = None,
        result: str | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        ai_messages: list[dict] | None = None,
        rejection_reason: str | None = None,
        queue_started_at: datetime | None = None,
        queue_completed_at: datetime | None = None,
    ) -> SubagentResult | None:
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None:
                return None
            changed = False
            if status is not None and current.status != status:
                current.status = status
                changed = True
            if result is not None:
                current.result = result
                changed = True
            if error is not None:
                current.error = error
                changed = True
            if started_at is not None:
                current.started_at = started_at
                changed = True
            if completed_at is not None:
                current.completed_at = completed_at
                changed = True
            if ai_messages is not None:
                current.ai_messages = deepcopy(ai_messages)
                changed = True
            if rejection_reason is not None:
                current.rejection_reason = rejection_reason
                changed = True
            if queue_started_at is not None:
                current.queue_started_at = queue_started_at
                changed = True
            if queue_completed_at is not None:
                current.queue_completed_at = queue_completed_at
                changed = True
            if changed:
                current.updated_at = datetime.now()
                if current.status.is_terminal:
                    self._terminal_signals[job_id].notify_all()
            return deepcopy(current)

    def wait_for_terminal(self, job_id: str, timeout_seconds: float) -> SubagentResult | None:
        with self._lock:
            result = self._jobs.get(job_id)
            if result is None:
                return None
            if result.status.is_terminal:
                return deepcopy(result)
            signal = self._terminal_signals[job_id]
            signal.wait(timeout=timeout_seconds)
            result = self._jobs.get(job_id)
            return deepcopy(result) if result is not None else None

    def cleanup(self, job_id: str) -> bool:
        with self._lock:
            result = self._jobs.get(job_id)
            if result is None or not result.is_terminal:
                return False
            self._jobs.pop(job_id, None)
            self._events.pop(job_id, None)
            self._terminal_signals.pop(job_id, None)
            self._cancel_requested.discard(job_id)
            return True
