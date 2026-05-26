"""Thread-safe in-memory state store for subagent jobs."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime
from operator import attrgetter
from threading import Condition, Lock

from .contracts import SubagentEvent, SubagentResult, SubagentStatus


class SubagentJobStore:
    """In-memory store with condition-based wakeups for delegated jobs."""

    def __init__(
        self,
        *,
        max_events_per_job: int = 200,
        max_ai_messages_per_job: int = 12,
        max_retained_jobs: int = 64,
    ) -> None:
        self._jobs: dict[str, SubagentResult] = {}
        self._events: dict[str, deque[SubagentEvent]] = {}
        self._terminal_signals: dict[str, Condition] = {}
        self._cancel_requested: set[str] = set()
        self._max_events_per_job = max(1, max_events_per_job)
        self._max_ai_messages_per_job = max(0, max_ai_messages_per_job)
        self._max_retained_jobs = max(1, max_retained_jobs)
        self._lock = Lock()

    def configure_limits(
        self,
        *,
        max_events_per_job: int,
        max_ai_messages_per_job: int,
        max_retained_jobs: int,
    ) -> None:
        with self._lock:
            self._max_events_per_job = max(1, max_events_per_job)
            self._max_ai_messages_per_job = max(0, max_ai_messages_per_job)
            self._max_retained_jobs = max(1, max_retained_jobs)
            for job_id, events in list(self._events.items()):
                if events.maxlen == self._max_events_per_job:
                    continue
                self._events[job_id] = deque(events, maxlen=self._max_events_per_job)
            for result in self._jobs.values():
                result.ai_messages = self._trim_ai_messages(result.ai_messages)

    def create(self, result: SubagentResult) -> None:
        with self._lock:
            stored = deepcopy(result)
            stored.ai_messages = self._trim_ai_messages(stored.ai_messages)
            self._jobs[result.task_id] = stored
            self._events[result.task_id] = deque(maxlen=self._max_events_per_job)
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

    def _trim_ai_messages(self, messages: list[dict] | None) -> list[dict]:
        if not messages or self._max_ai_messages_per_job == 0:
            return []
        return deepcopy(messages[-self._max_ai_messages_per_job :])

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
                current.ai_messages = self._trim_ai_messages(ai_messages)
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

    def compact_terminal_payloads(self, job_id: str) -> bool:
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None or not current.status.is_terminal:
                return False
            current.ai_messages = self._trim_ai_messages(current.ai_messages)
            current.updated_at = datetime.now()
            return True

    def prune_terminal_jobs(
        self,
        *,
        now: datetime | None = None,
        terminal_retention_seconds: int = 3600,
        exclude_job_ids: set[str] | None = None,
    ) -> list[str]:
        with self._lock:
            if not self._jobs:
                return []
            current_time = now or datetime.now()
            terminal_cutoff = max(0, terminal_retention_seconds)
            excluded = exclude_job_ids or set()
            removable: list[SubagentResult] = []
            for result in self._jobs.values():
                if result.task_id in excluded:
                    continue
                if not result.status.is_terminal:
                    continue
                completed_at = result.completed_at or result.updated_at
                age_seconds = (current_time - completed_at).total_seconds()
                if age_seconds >= terminal_cutoff:
                    removable.append(result)

            excess_count = max(0, len(self._jobs) - self._max_retained_jobs)
            if excess_count > 0:
                terminal_jobs = sorted(
                    (item for item in self._jobs.values() if item.status.is_terminal and item.task_id not in excluded),
                    key=attrgetter("updated_at"),
                )
                removable.extend(terminal_jobs[:excess_count])

            removed: list[str] = []
            removable_by_id = {result.task_id: result for result in removable}
            for result in sorted(removable_by_id.values(), key=attrgetter("updated_at")):
                if result.task_id not in self._jobs:
                    continue
                self._jobs.pop(result.task_id, None)
                self._events.pop(result.task_id, None)
                self._terminal_signals.pop(result.task_id, None)
                self._cancel_requested.discard(result.task_id)
                removed.append(result.task_id)
            return removed

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
