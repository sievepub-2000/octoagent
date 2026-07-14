"""Start/stop wiring for the dispatcher background tasks."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI

from src.harness.dispatcher.dispatch import DispatchLoop
from src.harness.dispatcher.leader import LeaderLoop
from src.harness.dispatcher.schema import (
    close_pool,
    dispatcher_enabled,
    ensure_schema,
)
from src.harness.dispatcher.workers import (
    HeartbeatLoop,
    deregister_worker,
    register_worker,
)

logger = logging.getLogger(__name__)

_STATE_KEY = "dispatcher_state"


async def init_dispatcher(*, capabilities: dict[str, Any] | None = None) -> bool:
    """Bootstrap schema + register this worker. Idempotent."""
    if not dispatcher_enabled():
        logger.info("Dispatcher: disabled (OCTO_DISPATCHER_ENABLED!=1); skipping")
        return False
    if not await ensure_schema():
        return False
    return await register_worker(capabilities=capabilities)


async def start_dispatcher_task(app: FastAPI, *, capabilities: dict[str, Any] | None = None) -> None:
    """Start heartbeat + leader + dispatch loops on the given FastAPI app."""
    if not dispatcher_enabled():
        return
    ok = await init_dispatcher(capabilities=capabilities)
    if not ok:
        logger.warning("Dispatcher: init failed; loops will not start")
        return
    state = {
        "heartbeat": HeartbeatLoop(),
        "leader": LeaderLoop(),
        "dispatch": DispatchLoop(),
    }
    state["heartbeat"].start()
    state["leader"].start()
    state["dispatch"].start()
    setattr(app.state, _STATE_KEY, state)
    logger.info("Dispatcher: heartbeat + leader + dispatch loops started")


async def stop_dispatcher_task(app: FastAPI) -> None:
    state = getattr(app.state, _STATE_KEY, None)
    if state is None:
        return
    try:
        await state["dispatch"].stop()
    except Exception:
        logger.exception("Dispatcher: dispatch loop stop failed")
    try:
        await state["leader"].stop()
    except Exception:
        logger.exception("Dispatcher: leader loop stop failed")
    try:
        await state["heartbeat"].stop()
    except Exception:
        logger.exception("Dispatcher: heartbeat loop stop failed")
    try:
        await deregister_worker()
    except Exception:
        logger.exception("Dispatcher: deregister failed")
    try:
        await shutdown_dispatcher()
    except Exception:
        logger.exception("Dispatcher: pool close failed")
    setattr(app.state, _STATE_KEY, None)


async def shutdown_dispatcher() -> None:
    await close_pool()


__all__ = [
    "init_dispatcher",
    "shutdown_dispatcher",
    "start_dispatcher_task",
    "stop_dispatcher_task",
]
