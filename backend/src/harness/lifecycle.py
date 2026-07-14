"""Orphan LangGraph run observer.

A *run* (in LangGraph parlance) becomes orphaned when it is marked `running`
or `pending` in the queue but no worker is actively producing tokens.

This sweeper combines two signals:

1. **Age-based** (always on): observe any run whose ``created_at`` is older
   than ``OCTO_HARNESS_MAX_RUN_AGE_MIN`` (default 10 min).
2. **Heartbeat-based** (opt-in via ``OCTO_HARNESS_RUN_JOURNAL=1``): consult
    the Postgres run journal and observe any run whose ``heartbeat_at`` is
   older than ``OCTO_HARNESS_RUN_HEARTBEAT_STALE_SEC`` (default 120s),
   regardless of total age. This catches genuinely-hung long-running tool
   calls that the age check would miss.
3. **Startup orphan flag**: no longer marks rows cancelled by default.

Cancellation is disabled by default because the OOM guard is the only hard
runtime stop. Set ``OCTO_HARNESS_ORPHAN_CANCEL_ENABLED=1`` only for manual
operator recovery.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _langgraph_base_url() -> str:
    return os.getenv("OCTO_LANGGRAPH_BASE_URL", "http://localhost:19804").rstrip("/")


def _max_run_age_minutes() -> int:
    raw = os.getenv("OCTO_HARNESS_MAX_RUN_AGE_MIN", "10").strip()
    try:
        v = int(raw)
        return v if v >= 1 else 10
    except ValueError:
        return 10


def _sweep_interval_seconds() -> int:
    raw = os.getenv("OCTO_HARNESS_SWEEP_INTERVAL_SEC", "60").strip()
    try:
        v = int(raw)
        return v if v >= 10 else 60
    except ValueError:
        return 60


def _orphan_cancel_enabled() -> bool:
    return os.getenv("OCTO_HARNESS_ORPHAN_CANCEL_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def _activity_window_minutes() -> int:
    """Grace window: if the thread had a message in the last N minutes, the run
    is still considered active even if its total age exceeds max_age."""
    raw = os.getenv("OCTO_HARNESS_ACTIVITY_WINDOW_MIN", "8").strip()
    try:
        v = int(raw)
        return v if v >= 1 else 8
    except ValueError:
        return 8


def _parse_ts(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    s = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


class OrphanRunSweeper:
    """Observes stale `pending`/`running` LangGraph runs; cancellation is opt-in."""

    def __init__(
        self,
        base_url: str | None = None,
        max_age: timedelta | None = None,
        request_timeout: float = 5.0,
    ) -> None:
        self.base_url = (base_url or _langgraph_base_url()).rstrip("/")
        self.max_age = max_age or timedelta(minutes=_max_run_age_minutes())
        self.request_timeout = request_timeout

    async def _list_busy_threads(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        try:
            r = await client.post(
                f"{self.base_url}/threads/search",
                json={"status": "busy", "limit": 100},
                timeout=self.request_timeout,
            )
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
        except Exception:
            logger.exception("OrphanRunSweeper: failed to list busy threads")
            return []

    async def _list_runs(self, client: httpx.AsyncClient, thread_id: str) -> list[dict[str, Any]]:
        try:
            r = await client.get(
                f"{self.base_url}/threads/{thread_id}/runs",
                timeout=self.request_timeout,
            )
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
        except Exception:
            logger.exception("OrphanRunSweeper: failed to list runs for thread %s", thread_id)
            return []

    async def _cancel_run(
        self,
        client: httpx.AsyncClient,
        thread_id: str,
        run_id: str,
    ) -> bool:
        try:
            r = await client.post(
                f"{self.base_url}/threads/{thread_id}/runs/{run_id}/cancel",
                params={"wait": "false", "action": "interrupt"},
                timeout=self.request_timeout,
            )
            if r.status_code in (200, 202, 204, 404):
                return True
            logger.warning(
                "OrphanRunSweeper: unexpected cancel status %s for %s/%s",
                r.status_code,
                thread_id,
                run_id,
            )
            return False
        except Exception:
            logger.exception("OrphanRunSweeper: cancel failed for thread=%s run=%s", thread_id, run_id)
            return False

    async def _sweep_via_journal(self, client: httpx.AsyncClient) -> dict[str, int]:
        """Heartbeat-based sweep using the Postgres journal."""
        from src.harness import run_journal as _rj

        out = {"journal_stale": 0, "journal_cancelled": 0}
        try:
            stale = await _rj.find_stale_runs()
        except Exception:
            logger.exception("OrphanRunSweeper: journal lookup failed")
            return out
        out["journal_stale"] = len(stale)
        for row in stale:
            tid = row.get("thread_id")
            rid = row.get("run_id")
            if not tid or not rid:
                continue
            if not _orphan_cancel_enabled():
                logger.warning("OrphanRunSweeper: observed heartbeat-stale run thread=%s run=%s", tid, rid)
                continue
            logger.warning("OrphanRunSweeper: cancelling heartbeat-stale run thread=%s run=%s", tid, rid)
            if await self._cancel_run(client, tid, rid):
                out["journal_cancelled"] += 1
                try:
                    await _rj.record_run_finished(rid, status="cancelled_stale_heartbeat")
                except Exception:
                    logger.exception("OrphanRunSweeper: journal update failed for %s", rid)
        return out

    async def _get_thread_last_message_time(self, client: httpx.AsyncClient, thread_id: str) -> datetime | None:
        """Return the timestamp of the most-recent message in the thread,
        or None if the state cannot be fetched."""
        try:
            r = await client.get(
                f"{self.base_url}/threads/{thread_id}/state",
                timeout=self.request_timeout,
            )
            if r.status_code != 200:
                return None
            state = r.json()
            messages = (state.get("values") or {}).get("messages", [])
            if not messages:
                return None
            # Walk in reverse to find the newest timestamped message
            for msg in reversed(messages):
                ts = None
                for key in ("created_at", "timestamp", "response_metadata"):
                    val = msg.get(key)
                    if isinstance(val, dict):
                        # response_metadata often has a 'created_at' subkey
                        val = val.get("created_at") or val.get("timestamp")
                    if val and isinstance(val, str):
                        ts = _parse_ts(val)
                        if ts:
                            return ts
            return None
        except Exception:
            return None

    async def sweep_once(self) -> dict[str, int]:
        now = datetime.now(UTC)
        result = {
            "threads_scanned": 0,
            "runs_inspected": 0,
            "runs_observed": 0,
            "runs_cancelled": 0,
            "journal_stale": 0,
            "journal_cancelled": 0,
        }

        async with httpx.AsyncClient() as client:
            # Age-based pass
            threads = await self._list_busy_threads(client)
            result["threads_scanned"] = len(threads)
            for th in threads:
                tid = th.get("thread_id") or th.get("id")
                if not tid:
                    continue
                runs = await self._list_runs(client, tid)
                for run in runs:
                    result["runs_inspected"] += 1
                    status = (run.get("status") or "").lower()
                    if status not in ("pending", "running"):
                        continue
                    created = _parse_ts(run.get("created_at"))
                    if created is None:
                        continue
                    age = now - created
                    if age < self.max_age:
                        continue
                    # Activity guard: skip cancel if the thread had a recent
                    # message (active tool-streaming may take > max_age).
                    if _orphan_cancel_enabled():
                        _activity_win = timedelta(minutes=_activity_window_minutes())
                        _last_msg = await self._get_thread_last_message_time(client, tid)
                        if _last_msg is not None and (now - _last_msg) < _activity_win:
                            logger.debug(
                                "OrphanRunSweeper: skipping active run thread=%s age=%.0fs last_msg_age=%.0fs",
                                tid,
                                age.total_seconds(),
                                (now - _last_msg).total_seconds(),
                            )
                            continue
                    rid = run.get("run_id") or run.get("id")
                    if not rid:
                        continue
                    result["runs_observed"] += 1
                    if not _orphan_cancel_enabled():
                        logger.warning(
                            "OrphanRunSweeper: observed orphan run thread=%s run=%s status=%s age=%.0fs",
                            tid,
                            rid,
                            status,
                            age.total_seconds(),
                        )
                        continue
                    logger.warning(
                        "OrphanRunSweeper: cancelling orphan run thread=%s run=%s status=%s age=%.0fs",
                        tid,
                        rid,
                        status,
                        age.total_seconds(),
                    )
                    ok = await self._cancel_run(client, tid, rid)
                    if ok:
                        result["runs_cancelled"] += 1

            # Heartbeat-based pass (journal opt-in)
            journal_out = await self._sweep_via_journal(client)
            result["journal_stale"] = journal_out["journal_stale"]
            result["journal_cancelled"] = journal_out["journal_cancelled"]
        return result

    async def run_forever(self, interval: int | None = None) -> None:
        gap = interval or _sweep_interval_seconds()
        logger.info(
            "OrphanRunSweeper: started (interval=%ss, max_age=%smin, base=%s)",
            gap,
            int(self.max_age.total_seconds() // 60),
            self.base_url,
        )
        while True:
            try:
                report = await self.sweep_once()
                if report["runs_cancelled"] > 0 or report["journal_cancelled"] > 0:
                    logger.info("OrphanRunSweeper: sweep report %s", report)
                else:
                    logger.debug("OrphanRunSweeper: sweep report %s", report)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("OrphanRunSweeper: sweep iteration crashed")
            await asyncio.sleep(gap)


async def sweep_orphaned_runs_once() -> dict[str, int]:
    return await OrphanRunSweeper().sweep_once()


def start_orphan_run_sweeper_task(app) -> None:
    try:
        sweeper = OrphanRunSweeper()
        task = asyncio.create_task(sweeper.run_forever(), name="harness-orphan-sweeper")
        app.state.orphan_run_sweeper_task = task
        app.state.orphan_run_sweeper = sweeper
    except Exception:
        logger.exception("Failed to start orphan run sweeper task")


async def stop_orphan_run_sweeper_task(app) -> None:
    task = getattr(app.state, "orphan_run_sweeper_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
    app.state.orphan_run_sweeper_task = None
