"""Memory auto-cleanup scheduler.

Provides TTL-based eviction, confidence-threshold pruning, and duplicate
deduplication for the SystemRAGStore.  A background scheduler runs hourly
(configurable) to keep the store healthy without manual intervention.

Usage — call ``start_cleanup_scheduler()`` once from the gateway lifespan.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.memory.system_rag_store import SystemRAGStore

logger = logging.getLogger(__name__)

# ── tunables (all overridable at runtime via environment / config) ─────────
_DEFAULT_INTERVAL_SECONDS = 3600  # run hourly
_DEFAULT_MIN_CONFIDENCE = 0.3  # prune entries below this confidence
_DEFAULT_MAX_ENTRIES_PER_NS = 100  # hard cap per namespace


class MemoryCleanupScheduler:
    """Periodic background task that evicts expired / low-quality memories.

    Runs in a daemon thread so it never blocks the main process.

    Eviction rules (executed in order):
      1. TTL: remove entries whose ``expires_at`` is in the past.
      2. Confidence floor: remove entries below ``min_confidence``.
      3. Namespace cap: when a namespace exceeds ``max_entries_per_ns``,
         evict the oldest / lowest-score entries until the cap is met.
    """

    def __init__(
        self,
        store: SystemRAGStore,
        *,
        interval_seconds: int = _DEFAULT_INTERVAL_SECONDS,
        min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
        max_entries_per_ns: int = _DEFAULT_MAX_ENTRIES_PER_NS,
    ) -> None:
        self._store = store
        self._interval = max(60, interval_seconds)
        self._min_confidence = min_confidence
        self._max_entries_per_ns = max_entries_per_ns
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_run: datetime | None = None
        self._stats: dict[str, int] = {}

    # ── public API ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background scheduler thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.debug("MemoryCleanupScheduler already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="memory-cleanup-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "MemoryCleanupScheduler started (interval=%ds, min_confidence=%.2f, max_entries_per_ns=%d)",
            self._interval,
            self._min_confidence,
            self._max_entries_per_ns,
        )

    def stop(self) -> None:
        """Signal the scheduler to stop after the current cycle finishes."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        logger.info("MemoryCleanupScheduler stopped")

    def run_once(self) -> dict[str, int]:
        """Execute a single cleanup cycle synchronously (useful for testing)."""
        return self._cleanup()

    @property
    def last_run(self) -> datetime | None:
        return self._last_run

    @property
    def stats(self) -> dict[str, int]:
        """Stats from the most recent cleanup cycle."""
        return dict(self._stats)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── internal ───────────────────────────────────────────────────────────

    def _loop(self) -> None:
        """Main scheduler loop — sleep then clean."""
        # Stagger first run by 2 minutes so startup is not burdened
        self._stop_event.wait(timeout=120)
        while not self._stop_event.is_set():
            try:
                stats = self._cleanup()
                logger.info("MemoryCleanupScheduler cycle complete: %s", stats)
            except Exception:
                logger.exception("MemoryCleanupScheduler cycle error")
            self._stop_event.wait(timeout=self._interval)

    def _cleanup(self) -> dict[str, int]:
        stats: dict[str, int] = {
            "ttl_evicted": 0,
            "confidence_pruned": 0,
            "cap_evicted": 0,
            "duplicates_pruned": 0,
            "errors": 0,
        }
        now = datetime.now(UTC)

        try:
            from src.agents.memory.system_rag_store import ALLOWED_SYSTEM_MEMORY_NAMESPACES

            # Rule 1: TTL eviction via built-in cleanup_expired
            try:
                result = self._store.cleanup_expired()
                stats["ttl_evicted"] = result.get("deleted_count", 0)
            except Exception:
                logger.exception("MemoryCleanupScheduler: TTL eviction failed")
                stats["errors"] += 1

            # Rules 2+3: confidence floor + namespace cap per namespace
            for ns in ALLOWED_SYSTEM_MEMORY_NAMESPACES:
                try:
                    ns_stats = self._cleanup_namespace(ns, now)
                    stats["confidence_pruned"] += ns_stats.get("confidence_pruned", 0)
                    stats["cap_evicted"] += ns_stats.get("cap_evicted", 0)
                    stats["duplicates_pruned"] += ns_stats.get("duplicates_pruned", 0)
                except Exception:
                    logger.exception("Cleanup error in namespace %s", ns)
                    stats["errors"] += 1
        except Exception:
            logger.exception("MemoryCleanupScheduler: failed to enumerate namespaces")
            stats["errors"] += 1

        self._last_run = now
        self._stats = stats
        return stats

    def _cleanup_namespace(self, namespace: str, now: datetime) -> dict[str, int]:
        """Run confidence-floor and cap rules for a single namespace."""
        stats: dict[str, int] = {"confidence_pruned": 0, "cap_evicted": 0, "duplicates_pruned": 0}

        # Fetch active entries
        try:
            entries = self._store.maintenance_entries(namespace=namespace)
        except Exception:
            logger.debug("Could not list namespace %s", namespace)
            return stats

        low_confidence: list[str] = []
        for entry in entries:
            confidence = self._get_confidence(entry)
            if confidence < self._min_confidence:
                low_confidence.append(entry.id)

        # Remove low-confidence entries through the store so caches are invalidated.
        try:
            self._evict_ids_via_store(low_confidence)
            stats["confidence_pruned"] += len(low_confidence)
        except Exception:
            logger.debug("Confidence eviction unsupported for namespace %s", namespace)

        # Exact normalized-content deduplication. Entries are newest-first.
        seen_content: set[str] = set()
        duplicate_ids: list[str] = []
        low_confidence_set = set(low_confidence)
        for entry in entries:
            if entry.id in low_confidence_set:
                continue
            normalized = " ".join(str(entry.content).lower().split())
            if normalized in seen_content:
                duplicate_ids.append(entry.id)
            else:
                seen_content.add(normalized)
        self._evict_ids_via_store(duplicate_ids)
        stats["duplicates_pruned"] += len(duplicate_ids)

        # Cap: keep only top-N by confidence
        removed = set(low_confidence) | set(duplicate_ids)
        survivors = [e for e in entries if e.id not in removed]
        if len(survivors) > self._max_entries_per_ns:
            over_cap = len(survivors) - self._max_entries_per_ns
            # maintenance_entries is newest-first: at equal confidence, evict
            # the older entry (the one with the larger original index).
            ranked = sorted(
                enumerate(survivors),
                key=lambda item: (self._get_confidence(item[1]), -item[0]),
            )
            evict_ids = [entry.id for _, entry in ranked[:over_cap]]
            try:
                self._evict_ids_via_store(evict_ids)
                stats["cap_evicted"] += len(evict_ids)
            except Exception:
                logger.debug("Cap eviction unsupported for namespace %s", namespace)

        return stats

    def _evict_ids_via_store(self, ids: list[str]) -> None:
        """Evict a list of entry IDs by direct DuckDB DELETE (internal access)."""
        if not ids:
            return
        self._store.delete_ids(ids)

    def _get_confidence(self, entry: object) -> float:
        """Extract confidence score from entry metadata."""
        meta = getattr(entry, "metadata", {})
        if isinstance(meta, dict):
            try:
                return float(meta.get("confidence", 1.0))
            except (TypeError, ValueError):
                pass
        return 1.0


# ── singleton ──────────────────────────────────────────────────────────────

_scheduler: MemoryCleanupScheduler | None = None


def get_cleanup_scheduler() -> MemoryCleanupScheduler | None:
    """Return the running scheduler, or None if not started."""
    return _scheduler


def start_cleanup_scheduler(
    *,
    interval_seconds: int = _DEFAULT_INTERVAL_SECONDS,
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
    max_entries_per_ns: int = _DEFAULT_MAX_ENTRIES_PER_NS,
) -> MemoryCleanupScheduler:
    """Create and start the global cleanup scheduler (idempotent)."""
    global _scheduler
    if _scheduler is not None and _scheduler._thread is not None and _scheduler._thread.is_alive():
        logger.debug("Cleanup scheduler already running; returning existing instance")
        return _scheduler

    try:
        from src.agents.memory.system_rag_store import get_system_rag_store

        store = get_system_rag_store()
    except Exception as exc:
        logger.warning("Could not obtain SystemRAGStore for cleanup scheduler: %s", exc)
        raise

    _scheduler = MemoryCleanupScheduler(
        store,
        interval_seconds=interval_seconds,
        min_confidence=min_confidence,
        max_entries_per_ns=max_entries_per_ns,
    )
    _scheduler.start()
    return _scheduler


def stop_cleanup_scheduler() -> None:
    """Stop the global cleanup scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()
        _scheduler = None
