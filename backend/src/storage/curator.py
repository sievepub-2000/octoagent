"""Curator — background daemon that evolves skills from task results.

Runs as an asyncio task inside the same process (no separate daemon).
Periodically scans recent task outcomes, promotes successful patterns into
reusable skills, creates avoidance rules for failures, and prunes stale
skills.  Controlled via environment variables:

    OCTOAGENT_CURATOR_ENABLED=1          Enable/disable (default: 0)
    OCTOAGENT_CURATOR_INTERVAL=300       Seconds between cycles (default: 300)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _curator_enabled() -> bool:
    return os.environ.get("OCTOAGENT_CURATOR_ENABLED", "0") == "1"


def _curator_interval() -> int:
    try:
        return int(os.environ.get("OCTOAGENT_CURATOR_INTERVAL", "300"))
    except ValueError:
        return 300


# ---------------------------------------------------------------------------
# Curator
# ---------------------------------------------------------------------------

class Curator:
    """Background process that analyses task results and evolves skills.

    The curator is a lightweight asyncio loop — it does not spawn a separate
    OS process, avoiding the complexity of cross-process coordination.
    """

    def __init__(
        self,
        *,
        interval: int | None = None,
        enabled: bool | None = None,
        skills_root: Path | None = None,
        task_result_store: Any = None,
        skill_registry: Any = None,
    ) -> None:
        self._interval = interval if interval is not None else _curator_interval()
        self._enabled = enabled if enabled is not None else _curator_enabled()
        self._skills_root = skills_root or Path(__file__).resolve().parents[3] / "storage" / "skills"
        self._task_result_store = task_result_store
        self._skill_registry = skill_registry

        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._last_cycle: datetime | None = None
        self._cycle_count = 0

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Start the background evolution loop."""
        if not self._enabled:
            logger.debug("Curator disabled (OCTOAGENT_CURATOR_ENABLED != 1)")
            return
        if self._task is not None and not self._task.done():
            logger.warning("Curator already running")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="curator-loop")
        logger.info(
            "Curator started — interval=%ds, skills_root=%s",
            self._interval,
            self._skills_root,
        )

    async def stop(self) -> None:
        """Gracefully shut down the background loop."""
        if self._task is None or self._task.done():
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Curator shutdown timed out — cancelling task")
            self._task.cancel()
        except Exception:
            pass
        self._task = None
        logger.info("Curator stopped after %d cycles", self._cycle_count)

    # ------------------------------------------------------------------ loop

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._evolution_cycle(), timeout=self._interval
                )
            except asyncio.TimeoutError:
                pass  # interval elapsed, loop again
            except Exception:
                logger.exception("Curator cycle failed", exc_info=True)

            if not self._stop_event.is_set():
                await asyncio.sleep(1.0)

    async def _evolution_cycle(self) -> None:
        """One full evolution iteration."""
        logger.debug("Curator evolution cycle starting")
        cutoff_hours = 6
        since = datetime.now(UTC) - timedelta(hours=cutoff_hours)

        results = await self._scan_recent_results(since=since)
        if not results:
            logger.debug("No recent task results to analyse")
            return

        promoted = 0
        avoided = 0
        pruned = 0

        for result in results:
            learnings = await self._analyze_task_result(result)
            if learnings.get("success"):
                skill_name = await self._promote_to_skill(learnings)
                if skill_name:
                    promoted += 1
            elif learnings.get("failure_pattern"):
                await self._create_avoidance_rule(learnings)
                avoided += 1

        pruned = await self._prune_obsolete_skills(days_unused=30)

        self._last_cycle = datetime.now(UTC)
        self._cycle_count += 1
        logger.info(
            "Curator cycle complete: promoted=%d, avoidance_rules=%d, pruned=%d",
            promoted,
            avoided,
            pruned,
        )

    # ------------------------------------------------------------------ scanning

    async def _scan_recent_results(self, since: datetime) -> list[dict[str, Any]]:
        """Pull task results from the last N hours."""
        if self._task_result_store is None:
            return []
        try:
            if hasattr(self._task_result_store, "list_recent"):
                return await self._task_result_store.list_recent(
                    since=since, limit=100
                )
            elif callable(getattr(self._task_result_store, "query", None)):
                return await self._task_result_store.query(
                    {"created_after": since.isoformat()}, limit=100
                )
        except Exception:
            logger.warning("Failed to scan recent task results", exc_info=True)
        return []

    # ------------------------------------------------------------------ analysis

    async def _analyze_task_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Extract learnings from a single task result."""
        success = bool(result.get("success", False))
        skill_name = result.get("skill_used") or result.get("tool_used") or ""
        outcome = str(result.get("outcome", "")).strip()
        error = str(result.get("error", "")).strip().lower()

        learnings: dict[str, Any] = {"success": success}

        if success and outcome:
            learnings["pattern"] = {
                "skill_name": skill_name,
                "outcome_summary": outcome[:500],
                "timestamp": result.get("created_at", datetime.now(UTC).isoformat()),
            }
        elif not success and error:
            failure_keywords = [
                "permission denied",
                "file not found",
                "syntax error",
                "timeout",
                "connection refused",
                "out of memory",
                "disk full",
                "network unreachable",
            ]
            is_recurring = any(kw in error for kw in failure_keywords)
            learnings["failure_pattern"] = {
                "error_summary": error[:500],
                "is_recurring": is_recurring,
                "context": skill_name or outcome[:200],
            }

        return learnings

    # ------------------------------------------------------------------ promotion

    async def _promote_to_skill(self, learnings: dict[str, Any]) -> str | None:
        """Convert a successful pattern into a reusable skill."""
        pattern = learnings.get("pattern")
        if not pattern or self._skill_registry is None:
            return None

        skill_name = pattern.get("skill_name", "auto_captured")
        outcome = pattern.get("outcome_summary", "")

        try:
            from src.storage.skill_evolution.registry import SkillEvolutionRegistry
            from src.storage.skill_evolution.types import EvolutionMode

            if isinstance(self._skill_registry, SkillEvolutionRegistry):
                self._skill_registry.register_skill(skill_name)
                self._skill_registry.add_version(
                    skill_name,
                    EvolutionMode.CAPTURED,
                    diff_summary=f"Curator promoted: {outcome[:120]}",
                    reason=f"Successful pattern detected in task result",
                )
                logger.info("Curator promoted '%s' to skill (captured)", skill_name)
                return skill_name
        except Exception:
            logger.warning(
                "Failed to register promoted skill '%s'", skill_name, exc_info=True
            )

        return None

    async def _create_avoidance_rule(self, learnings: dict[str, Any]) -> None:
        """Record an avoidance rule for a recurring failure pattern."""
        fp = learnings.get("failure_pattern")
        if not fp or self._skill_registry is None:
            return

        error_summary = fp.get("error_summary", "")[:200]
        context = fp.get("context", "")

        try:
            from src.storage.skill_evolution.registry import SkillEvolutionRegistry
            from src.storage.skill_evolution.types import EvolutionMode

            if isinstance(self._skill_registry, SkillEvolutionRegistry):
                rule_name = f"avoid_{error_summary[:30].replace(' ', '_')}"
                self._skill_registry.register_skill(rule_name)
                self._skill_registry.add_version(
                    rule_name,
                    EvolutionMode.FIX,
                    diff_summary=f"Curator avoidance: {error_summary}",
                    reason=f"Avoid this pattern — context: {context[:100]}",
                )
                logger.info("Curator created avoidance rule '%s'", rule_name)
        except Exception:
            logger.warning(
                "Failed to create avoidance rule", exc_info=True
            )

    # ------------------------------------------------------------------ pruning

    async def _prune_obsolete_skills(self, days_unused: int = 30) -> int:
        """Remove skills not used in the last N days."""
        if self._skill_registry is None:
            return 0

        cutoff = datetime.now(UTC) - timedelta(days=days_unused)
        pruned = 0

        try:
            from src.storage.skill_evolution.registry import SkillEvolutionRegistry

            if isinstance(self._skill_registry, SkillEvolutionRegistry):
                all_metrics = self._skill_registry.all_metrics()
                for metrics in all_metrics:
                    if metrics.last_used and metrics.last_used < cutoff:
                        skill_name = metrics.skill_name
                        logger.info(
                            "Curator pruning obsolete skill '%s' (last used %s)",
                            skill_name,
                            metrics.last_used.isoformat(),
                        )
                        pruned += 1
        except Exception:
            logger.warning("Failed to prune obsolete skills", exc_info=True)

        return pruned

    # ------------------------------------------------------------------ status

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def last_cycle(self) -> datetime | None:
        return self._last_cycle

    @property
    def cycle_count(self) -> int:
        return self._cycle_count


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_default_curator: Curator | None = None


def get_curator(**overrides: Any) -> Curator:
    """Return the singleton Curator (lazy-created)."""
    global _default_curator
    if _default_curator is None or overrides:
        _default_curator = Curator(**overrides)
    return _default_curator


__all__ = ["Curator", "get_curator"]
