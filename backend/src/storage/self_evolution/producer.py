"""AutoProducer (Sprint-3 P0 — REAL).

Periodically scans recent lessons via the unified RAG facade and drafts
``EvolutionProposal`` entries for failure patterns that recur ≥ N times. Runs
as a daemon coroutine launched by ``gateway/lifecycle.py`` on startup.

Safety properties:
  * Append-only: never edits ``self_evolution/__init__.py``; instead it imports
    the existing facade and calls its public APIs.
  * Idempotent: dedupes by ``pattern`` digest before creating a proposal.
  * Bounded: at most ``max_proposals_per_scan`` drafts per cycle.
  * Default OFF — enable via env ``OCTOAGENT_AUTO_PRODUCER_ENABLED=1`` so the
    first deploy is observation-only.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.environ.get("OCTOAGENT_AUTO_PRODUCER_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class AutoProducer:
    """Scans LessonsStore for repeating patterns and drafts proposals."""

    def __init__(
        self,
        *,
        every_seconds: int = 1800,
        min_pattern_count: int = 3,
        max_proposals_per_scan: int = 2,
    ):
        self.every_seconds = max(60, every_seconds)
        self.min_pattern_count = max(2, min_pattern_count)
        self.max_proposals_per_scan = max(1, max_proposals_per_scan)
        self._seen_digests: set[str] = set()
        self._task: asyncio.Task | None = None

    async def scan_once(self) -> int:
        """Return number of proposals drafted in this scan."""
        if not _enabled():
            return 0
        try:
            # Lazy imports keep the cold-start fast.
            from src.storage.self_evolution import get_self_evolution_service
            from src.storage.self_evolution.lessons import LessonsStore

            store = LessonsStore.default()
            rows = store.recent(limit=200, min_severity=2)
        except Exception as exc:
            logger.debug("AutoProducer: scan skipped (%s)", exc)
            return 0

        if not rows:
            return 0

        patterns = Counter()
        sample: dict[str, dict[str, Any]] = {}
        for r in rows:
            pat = (r.get("pattern") or "").strip()
            if not pat:
                continue
            patterns[pat] += 1
            sample.setdefault(pat, r)

        drafted = 0
        try:
            service = get_self_evolution_service()
        except Exception as exc:
            logger.debug("AutoProducer: service unavailable (%s)", exc)
            return 0

        for pat, count in patterns.most_common():
            if count < self.min_pattern_count:
                break
            d = _digest(pat)
            if d in self._seen_digests:
                continue
            row = sample[pat]
            try:
                proposal = service.create_proposal(
                    change_type="prompt_patch",
                    title=f"Recurring failure pattern ({count}x)",
                    description=(f"Auto-detected from lessons store; category={row.get('category')} severity={row.get('severity')}. Pattern: {pat[:160]}"),
                    proposed_change={
                        "pattern": pat,
                        "fix_hint": row.get("fix") or "",
                        "occurrences": count,
                        "evidence_lesson_id": row.get("id"),
                    },
                    source="auto_producer",
                    tags=["auto_producer", "lessons"],
                )
                self._seen_digests.add(d)
                drafted += 1
                logger.info(
                    "AutoProducer drafted proposal id=%s (pattern=%s, count=%d)",
                    getattr(proposal, "proposal_id", "?"),
                    pat[:40],
                    count,
                )
            except Exception as exc:
                logger.debug("AutoProducer: propose failed for %s — %s", pat[:40], exc)
            if drafted >= self.max_proposals_per_scan:
                break
        return drafted

    async def run_forever(self) -> None:
        logger.info(
            "AutoProducer loop starting (every=%ds, min_count=%d, max_per_scan=%d, enabled=%s)",
            self.every_seconds,
            self.min_pattern_count,
            self.max_proposals_per_scan,
            _enabled(),
        )
        while True:
            try:
                n = await self.scan_once()
                if n:
                    logger.info("AutoProducer: drafted %d proposal(s)", n)
            except Exception as exc:  # noqa: BLE001
                logger.warning("AutoProducer cycle error: %s", exc)
            await asyncio.sleep(self.every_seconds)

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._task = loop.create_task(self.run_forever(), name="auto_producer")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None


_DEFAULT: AutoProducer | None = None


def get_default_producer() -> AutoProducer:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = AutoProducer()
    return _DEFAULT


__all__ = ["AutoProducer", "get_default_producer"]
