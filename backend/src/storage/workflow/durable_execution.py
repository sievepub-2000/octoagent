"""Durable-execution primitives for OctoAgent long-running workflows.

This module absorbs the *ideas* behind engine-backed durable execution
(Temporal-style) — deterministic replay, idempotent activities, and explicit
compensation (saga) — as a lightweight, dependency-free layer on top of the
existing LangGraph runtime. No external workflow engine is required: it narrows
the durability gap with engine-backed competitors while preserving OctoAgent's
single-truth ``task_workspaces`` model.

Three concerns, three primitives:

* ``IdempotentRunner`` — an activity runs **at most once** per idempotency key.
  Re-invocation with the same key replays the recorded result instead of
  re-executing the side effect (deterministic replay).
* ``Saga`` — orchestrates an ordered list of steps, each optionally paired with
  a compensation. If any step fails, the already-completed steps are rolled
  back by running their compensations in reverse order (explicit compensation).
* ``ReplayJournal`` — an append-only, serialisable record of every step outcome,
  so a run can be audited and deterministically replayed.

The layer is pure-Python and imports only the standard library, so it stays
inside the ``storage`` architecture boundary and is trivially unit-testable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

__all__ = [
    "StepStatus",
    "ActivityRecord",
    "InMemoryResultStore",
    "IdempotentRunner",
    "ReplayJournal",
    "Saga",
    "SagaAborted",
    "SagaResult",
    "make_idempotency_key",
]


def make_idempotency_key(name: str, *args: Any, **kwargs: Any) -> str:
    """Derive a stable idempotency key from an activity name and its arguments.

    The arguments are serialised deterministically (sorted keys, ``default=str``
    for non-JSON values) so the same logical call always yields the same key
    across processes and restarts.
    """
    payload = json.dumps(
        {"name": name, "args": args, "kwargs": kwargs},
        sort_keys=True,
        default=str,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{name}:{digest}"


class StepStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    REPLAYED = "replayed"
    FAILED = "failed"
    COMPENSATED = "compensated"


@dataclass(frozen=True)
class ActivityRecord:
    key: str
    name: str
    status: StepStatus
    result_json: str | None
    ts: float

    def result(self) -> Any:
        if self.result_json is None:
            return None
        return json.loads(self.result_json)


class InMemoryResultStore:
    """Process-local idempotency store.

    Mapping of ``idempotency key -> ActivityRecord``. The default backing for
    :class:`IdempotentRunner`; a persistent (DuckDB/Postgres) implementation can
    expose the same ``get``/``put`` surface without changing callers.
    """

    def __init__(self) -> None:
        self._records: dict[str, ActivityRecord] = {}

    def get(self, key: str) -> ActivityRecord | None:
        return self._records.get(key)

    def put(self, record: ActivityRecord) -> None:
        self._records[record.key] = record

    def __contains__(self, key: str) -> bool:
        return key in self._records

    def __len__(self) -> int:
        return len(self._records)


class IdempotentRunner:
    """Run side-effecting activities **at most once** per idempotency key.

    On first call the activity executes, its (JSON-serialisable) result is
    recorded, and the result is returned. On any subsequent call with the same
    key the recorded result is replayed without re-executing the activity — the
    deterministic-replay guarantee that makes retries and crash-recovery safe.
    """

    def __init__(self, store: InMemoryResultStore | None = None) -> None:
        self._store = store or InMemoryResultStore()

    @property
    def store(self) -> InMemoryResultStore:
        return self._store

    def run(self, key: str, activity: Callable[[], T], *, name: str | None = None) -> T:
        existing = self._store.get(key)
        if existing is not None and existing.status in (StepStatus.COMPLETED, StepStatus.REPLAYED):
            logger.debug("durable: replaying activity key=%s (no side effect)", key)
            return existing.result()

        result = activity()
        try:
            result_json = json.dumps(result, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            result_json = json.dumps(str(result), ensure_ascii=False)
        self._store.put(
            ActivityRecord(
                key=key,
                name=name or key,
                status=StepStatus.COMPLETED,
                result_json=result_json,
                ts=time.time(),
            )
        )
        return result


@dataclass
class _JournalEntry:
    step: str
    status: StepStatus
    detail: str | None = None
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"step": self.step, "status": self.status.value, "detail": self.detail, "ts": self.ts}


class ReplayJournal:
    """Append-only, serialisable record of step outcomes for audit/replay."""

    def __init__(self) -> None:
        self._entries: list[_JournalEntry] = []

    def append(self, step: str, status: StepStatus, detail: str | None = None) -> None:
        self._entries.append(_JournalEntry(step=step, status=status, detail=detail))

    @property
    def entries(self) -> list[_JournalEntry]:
        return list(self._entries)

    def statuses(self) -> list[StepStatus]:
        return [e.status for e in self._entries]

    def to_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._entries]


class SagaAborted(RuntimeError):
    """Raised when a saga step fails and compensations have been applied."""

    def __init__(self, failed_step: str, original: BaseException, journal: ReplayJournal) -> None:
        super().__init__(f"saga aborted at step {failed_step!r}: {original}")
        self.failed_step = failed_step
        self.original = original
        self.journal = journal


@dataclass(frozen=True)
class SagaResult:
    completed_steps: list[str]
    results: dict[str, Any]
    journal: ReplayJournal


@dataclass
class _SagaStep[T]:
    name: str
    action: Callable[[], T]
    compensation: Callable[[], None] | None
    key: str | None


class Saga:
    """Ordered steps with explicit compensation and deterministic replay.

    Each ``step`` couples a forward ``action`` with an optional ``compensation``.
    ``execute`` runs the actions in order (idempotently, keyed by ``key`` or the
    step name). If a step raises, every already-completed step is rolled back by
    invoking its compensation in reverse order, the journal records the outcome,
    and :class:`SagaAborted` is raised carrying the journal for auditing.
    """

    def __init__(self, runner: IdempotentRunner | None = None) -> None:
        self._steps: list[_SagaStep[Any]] = []
        self._runner = runner or IdempotentRunner()
        self._journal = ReplayJournal()

    @property
    def journal(self) -> ReplayJournal:
        return self._journal

    def step(
        self,
        name: str,
        action: Callable[[], T],
        compensation: Callable[[], None] | None = None,
        *,
        key: str | None = None,
    ) -> Saga:
        self._steps.append(_SagaStep(name=name, action=action, compensation=compensation, key=key))
        return self

    def execute(self) -> SagaResult:
        completed: list[str] = []
        compensations: list[tuple[str, Callable[[], None]]] = []
        results: dict[str, Any] = {}

        for s in self._steps:
            run_key = s.key or make_idempotency_key(s.name)
            already = self._runner.store.get(run_key) is not None
            try:
                value = self._runner.run(run_key, s.action, name=s.name)
            except BaseException as exc:  # noqa: BLE001 - we re-raise as SagaAborted
                self._journal.append(s.name, StepStatus.FAILED, detail=str(exc))
                self._compensate(compensations)
                raise SagaAborted(s.name, exc, self._journal) from exc

            results[s.name] = value
            completed.append(s.name)
            if s.compensation is not None:
                compensations.append((s.name, s.compensation))
            self._journal.append(
                s.name,
                StepStatus.REPLAYED if already else StepStatus.COMPLETED,
            )

        return SagaResult(completed_steps=completed, results=results, journal=self._journal)

    def _compensate(self, compensations: list[tuple[str, Callable[[], None]]]) -> None:
        for name, comp in reversed(compensations):
            try:
                comp()
                self._journal.append(name, StepStatus.COMPENSATED)
            except Exception as exc:  # noqa: BLE001 - best-effort rollback, keep going
                logger.warning("durable: compensation for step %s failed: %s", name, exc)
                self._journal.append(name, StepStatus.FAILED, detail=f"compensation failed: {exc}")
