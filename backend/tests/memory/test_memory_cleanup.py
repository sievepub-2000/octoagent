from dataclasses import dataclass, field

from src.agents.memory.cleanup import MemoryCleanupScheduler


@dataclass
class _Entry:
    id: str
    content: str
    metadata: dict = field(default_factory=dict)


class _Store:
    def __init__(self, entries: list[_Entry]) -> None:
        self.entries = entries
        self.deleted: list[str] = []

    def maintenance_entries(self, *, namespace: str) -> list[_Entry]:
        return list(self.entries)

    def delete_ids(self, ids: list[str]) -> int:
        self.deleted.extend(ids)
        return len(ids)


def test_cleanup_prunes_low_confidence_duplicates_and_oldest_over_cap() -> None:
    store = _Store(
        [
            _Entry("new", "unique new", {"confidence": 0.9}),
            _Entry("duplicate", " Same   fact ", {"confidence": 0.95}),
            _Entry("original", "same fact", {"confidence": 0.95}),
            _Entry("old", "unique old", {"confidence": 0.9}),
            _Entry("weak", "weak", {"confidence": 0.1}),
        ]
    )
    scheduler = MemoryCleanupScheduler(store, min_confidence=0.3, max_entries_per_ns=2)

    stats = scheduler._cleanup_namespace("system_insight", None)

    assert stats == {"confidence_pruned": 1, "duplicates_pruned": 1, "cap_evicted": 1}
    assert store.deleted == ["weak", "original", "old"]
