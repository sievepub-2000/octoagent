"""One-shot maintenance: clear `pending_sends` referencing unknown nodes from the in-memory checkpoint DB.

For the in-process langgraph_runtime_inmem variant we use, pending sends live in the
runtime tasks table. After graph schema changes, old checkpoints may reference removed
nodes (e.g. legacy "tools" node) — langgraph then logs:
   `Ignoring unknown node name tools in pending sends`
which is cosmetic but signals stale state.

This script connects via the langgraph SDK and rewrites the latest state for every
thread, effectively dropping orphaned pending sends without losing message history.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from langgraph_sdk import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cleanup_pending_sends")


async def _run(base_url: str, dry_run: bool) -> int:
    client = get_client(url=base_url)
    threads = await client.threads.search(limit=500)
    log.info("Found %d threads", len(threads))
    cleaned = 0
    for t in threads:
        thread_id = t["thread_id"]
        try:
            state = await client.threads.get_state(thread_id)
        except Exception as exc:
            log.warning("skip %s: %s", thread_id, exc)
            continue
        tasks = state.get("tasks") or []
        orphans = [task for task in tasks if not task.get("name") or task.get("name") == "tools"]
        if not orphans:
            continue
        log.info("thread %s has %d orphan task(s)", thread_id, len(orphans))
        if dry_run:
            continue
        # Rewriting state via update_state with same values clears pending sends.
        values = state.get("values") or {}
        try:
            await client.threads.update_state(thread_id, values=values)
            cleaned += 1
        except Exception as exc:
            log.warning("rewrite failed for %s: %s", thread_id, exc)
    log.info("cleanup complete: cleaned=%d (dry_run=%s)", cleaned, dry_run)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("LANGGRAPH_URL", "http://127.0.0.1:19880/api/langgraph"))
    parser.add_argument("--apply", action="store_true", help="Actually rewrite state. Default is dry-run.")
    args = parser.parse_args()
    return asyncio.run(_run(args.base_url, dry_run=not args.apply))


if __name__ == "__main__":
    sys.exit(main())
