from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter

router = APIRouter(prefix="/api/agent-runtime", tags=["agent-runtime"])


def _snapshot() -> dict:
    import psycopg

    dsn = os.getenv("OCTOAGENT_CHECKPOINTER_DSN")
    checkpoints = 0
    threads = 0
    if dsn:
        with psycopg.connect(dsn, connect_timeout=3) as conn, conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM checkpoints")
            checkpoints = int(cursor.fetchone()[0])
            cursor.execute("SELECT count(DISTINCT thread_id) FROM checkpoints")
            threads = int(cursor.fetchone()[0])
    return {
        "module": "agent-runtime",
        "graph": "lead_agent",
        "protocol": "langgraph",
        "persistence": "postgres",
        "threads": threads,
        "checkpoints": checkpoints,
        "permission_modes": ["approval", "directory", "system"],
        "data_concepts": ["project", "task", "run", "run_event"],
        "harness_interface": "/api/harness",
    }


@router.get("", summary="Get the live Agent Runtime snapshot")
async def get_agent_runtime_snapshot() -> dict:
    return await asyncio.to_thread(_snapshot)
