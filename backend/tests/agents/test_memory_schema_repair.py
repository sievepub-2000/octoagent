from __future__ import annotations

from src.agents.memory.updater import MemoryUpdater, ensure_memory_schema
from src.gateway.routers.memory import _normalize_memory_snapshot


def test_ensure_memory_schema_preserves_legacy_facts() -> None:
    repaired = ensure_memory_schema(
        {
            "user_context": "User works on OctoAgent.",
            "history": [],
            "facts": [
                {
                    "id": "fact_1",
                    "content": "User prefers Chinese responses.",
                    "category": "preference",
                    "confidence": 0.9,
                    "createdAt": "2026-05-12T00:00:00Z",
                    "source": "thread_1",
                }
            ],
        }
    )

    assert repaired["user"]["topOfMind"]["summary"] == "User works on OctoAgent."
    assert repaired["history"]["recentMonths"]["summary"] == ""
    assert repaired["facts"][0]["content"] == "User prefers Chinese responses."


def test_apply_updates_handles_legacy_memory_and_backfills_summary() -> None:
    updater = MemoryUpdater()
    updated = updater._apply_updates(
        {"user_context": "", "history": [], "facts": []},
        {
            "user": {},
            "history": {},
            "newFacts": [
                {
                    "content": "User is repairing OctoAgent memory summaries.",
                    "category": "goal",
                    "confidence": 0.9,
                }
            ],
            "factsToRemove": [],
        },
        thread_id="thread_1",
    )

    assert updated["facts"]
    assert "OctoAgent memory summaries" in updated["user"]["topOfMind"]["summary"]
    assert "OctoAgent memory summaries" in updated["history"]["recentMonths"]["summary"]


def test_apply_updates_attaches_context_cycle_metadata_to_new_facts() -> None:
    updater = MemoryUpdater()
    updated = updater._apply_updates(
        {"user_context": "", "history": [], "facts": []},
        {
            "user": {},
            "history": {},
            "newFacts": [
                {
                    "content": "User wants context compression cycles to reset the token lamp.",
                    "category": "preference",
                    "confidence": 0.9,
                }
            ],
            "factsToRemove": [],
        },
        thread_id="thread_1",
        metadata={"context_cycle_id": "context-cycle-test", "compaction_trigger": "gateway_85_percent"},
    )

    assert updated["facts"][0]["sourceMetadata"]["context_cycle_id"] == "context-cycle-test"
    assert updated["facts"][0]["sourceMetadata"]["compaction_trigger"] == "gateway_85_percent"


def test_apply_updates_skips_duplicate_completed_item_in_same_task_phase() -> None:
    updater = MemoryUpdater()
    metadata = {
        "task_phase_id": "task-phase-test",
        "source_event_id": "compaction-event-1",
        "completed_item_hashes": ["hash-completed-1"],
        "compaction_trigger": "gateway_85_percent",
    }
    first = updater._apply_updates(
        {"user_context": "", "history": [], "facts": []},
        {
            "user": {},
            "history": {},
            "newFacts": [
                {
                    "content": "Completed proxy repair validation.",
                    "category": "task",
                    "confidence": 0.9,
                }
            ],
            "factsToRemove": [],
        },
        thread_id="thread_1",
        metadata=metadata,
    )
    second = updater._apply_updates(
        first,
        {
            "user": {},
            "history": {},
            "newFacts": [
                {
                    "content": "Completed proxy repair validation again.",
                    "category": "task",
                    "confidence": 0.9,
                }
            ],
            "factsToRemove": [],
        },
        thread_id="thread_1",
        metadata={**metadata, "source_event_id": "compaction-event-2"},
    )

    assert len(second["facts"]) == 1
    assert second["facts"][0]["taskPhaseId"] == "task-phase-test"
    assert second["facts"][0]["completedItemHash"] == "hash-completed-1"
    assert second["task_phases"]["task-phase-test"]["completedItemHashes"] == ["hash-completed-1"]


def test_memory_api_snapshot_backfills_overview_from_facts() -> None:
    normalized = _normalize_memory_snapshot(
        {
            "user_context": "",
            "history": [],
            "facts": [
                {
                    "id": "fact_1",
                    "content": "User requested a trust-score observer repair.",
                    "category": "goal",
                    "confidence": 0.9,
                    "createdAt": "2026-05-12T00:00:00Z",
                    "source": "thread_1",
                }
            ],
            "lastUpdated": "2026-05-12T00:00:00Z",
        }
    )

    assert "trust-score observer" in normalized["user"]["workContext"]["summary"]
    assert "trust-score observer" in normalized["history"]["longTermBackground"]["summary"]
