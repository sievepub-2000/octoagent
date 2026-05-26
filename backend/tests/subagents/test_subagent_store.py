from __future__ import annotations

from datetime import datetime, timedelta

from src.runtime.config.subagents_config import load_subagents_config_from_dict
from src.agents.subagents.contracts import SubagentEvent, SubagentResult, SubagentStatus
from src.agents.subagents.policy import check_admission
from src.agents.subagents.store import SubagentJobStore


def _result(task_id: str, status: SubagentStatus = SubagentStatus.COMPLETED) -> SubagentResult:
    now = datetime.now() - timedelta(hours=2)
    return SubagentResult(
        task_id=task_id,
        trace_id=f"trace-{task_id}",
        status=status,
        completed_at=now if status.is_terminal else None,
        updated_at=now,
    )


def test_store_bounds_events_and_ai_messages() -> None:
    store = SubagentJobStore(max_events_per_job=2, max_ai_messages_per_job=1)
    store.create(_result("job-1", SubagentStatus.RUNNING))

    store.update("job-1", ai_messages=[{"id": "a"}, {"id": "b"}])
    for index in range(3):
        store.append_event(
            SubagentEvent(
                sequence=index + 1,
                job_id="job-1",
                event_type=f"event-{index}",
                status=SubagentStatus.RUNNING,
            )
        )

    assert store.get("job-1").ai_messages == [{"id": "b"}]
    events = store.pop_events("job-1")
    assert [event.event_type for event in events] == ["event-1", "event-2"]


def test_store_prunes_terminal_history_without_touching_active_jobs() -> None:
    store = SubagentJobStore(max_retained_jobs=2)
    store.create(_result("old-1"))
    store.create(_result("old-2"))
    store.create(_result("active", SubagentStatus.RUNNING))

    removed = store.prune_terminal_jobs(terminal_retention_seconds=1)

    assert removed == ["old-1", "old-2"]
    assert store.get("active") is not None


def test_admission_rejects_when_global_job_ceiling_is_reached() -> None:
    try:
        load_subagents_config_from_dict(
            {
                "max_total_subagent_jobs": 2,
                "max_concurrent_subagents": 10,
                "enable_system_memory_guard": False,
            }
        )

        reason = check_admission([_result("one"), _result("two")], thread_id=None)

        assert reason is not None
        assert "Global delegated-task ceiling" in reason
    finally:
        load_subagents_config_from_dict({})