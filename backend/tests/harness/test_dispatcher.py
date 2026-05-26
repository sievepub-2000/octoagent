"""Unit tests for the Phase 6 dispatcher modules.

Runs without a live Postgres: every public function is contracted to
return safe defaults when DSN resolution fails or the dispatcher flag
is unset. Uses ``asyncio.run`` (the repo convention — see
``tests/unit/test_oom_guard.py``) since ``pytest-asyncio`` is not a
project dependency.
"""

from __future__ import annotations

import asyncio

import pytest

from src.harness.dispatcher import (
    ack_dispatch,
    claim_dispatch,
    dispatch_queue_stats,
    drain_self,
    enqueue_dispatch,
    is_leader,
    leader_status,
    list_workers,
    mark_draining,
    nack_dispatch,
    worker_id,
)
from src.harness.dispatcher.bus_backend import (
    PostgresInboundBus,
    _from_payload,
    _to_payload,
    bus_backend_is_postgres,
    maybe_install_postgres_bus_backend,
)
from src.harness.dispatcher.leader import LeaderLoop
from src.harness.dispatcher.queue import _backoff_seconds, _safe_channel
from src.harness.dispatcher.schema import dispatcher_enabled


@pytest.fixture(autouse=True)
def _ensure_disabled(monkeypatch):
    """Default-off: clear the flag for every test unless re-set."""
    monkeypatch.delenv("OCTO_DISPATCHER_ENABLED", raising=False)
    monkeypatch.delenv("OCTO_DISPATCH_BACKEND", raising=False)
    yield


def test_dispatcher_disabled_by_default():
    assert dispatcher_enabled() is False


def test_worker_id_stable_within_process():
    a = worker_id()
    b = worker_id()
    assert a == b
    parts = a.split(":")
    assert len(parts) == 3
    assert parts[1].isdigit()
    assert len(parts[2]) >= 4


def test_workers_api_noop_when_disabled():
    assert asyncio.run(list_workers()) == []
    assert asyncio.run(mark_draining()) is False


def test_queue_api_noop_when_disabled():
    assert asyncio.run(enqueue_dispatch("any", {"k": "v"})) is None
    assert asyncio.run(claim_dispatch()) is None
    assert asyncio.run(ack_dispatch("nonexistent")) is False
    assert asyncio.run(nack_dispatch("nonexistent")) is None


def test_dispatch_queue_stats_disabled_shape():
    stats = asyncio.run(dispatch_queue_stats())
    assert stats == {"enabled": False, "by_state": {}, "by_kind": {}, "in_flight": 0}


def test_leader_status_default():
    assert is_leader() is False
    s = leader_status()
    assert s["worker_id"] == worker_id()
    assert s["is_leader"] is False
    assert s["since"] is None


def test_leader_loop_start_noop_when_disabled():
    async def _go():
        loop = LeaderLoop()
        loop.start()
        assert loop._task is None
        await loop.stop()

    asyncio.run(_go())


def test_drain_self_disabled():
    out = asyncio.run(drain_self())
    assert out["drained"] is True
    assert out["remaining"] == 0
    assert out["enabled"] is False


def test_backoff_curve():
    assert _backoff_seconds(0) == 1
    assert _backoff_seconds(1) == 2
    assert _backoff_seconds(2) == 4
    assert _backoff_seconds(3) == 8
    assert _backoff_seconds(8) == 256
    assert _backoff_seconds(20) == 300


def test_safe_channel_name():
    assert _safe_channel("channel_inbound") == "channel_inbound"
    assert _safe_channel("kind with spaces & punct!") == "kind_with_spaces___punct_"
    assert _safe_channel("") == "generic"
    assert len(_safe_channel("x" * 64)) == 32


def test_bus_backend_default_inmemory(monkeypatch):
    monkeypatch.delenv("OCTO_DISPATCHER_ENABLED", raising=False)
    monkeypatch.delenv("OCTO_DISPATCH_BACKEND", raising=False)
    assert bus_backend_is_postgres() is False
    bus = maybe_install_postgres_bus_backend()
    assert type(bus).__name__ == "MessageBus"


def test_bus_backend_postgres_when_flagged(monkeypatch):
    monkeypatch.setenv("OCTO_DISPATCHER_ENABLED", "1")
    monkeypatch.setenv("OCTO_DISPATCH_BACKEND", "postgres")
    assert bus_backend_is_postgres() is True
    bus = maybe_install_postgres_bus_backend()
    assert isinstance(bus, PostgresInboundBus)


def test_bus_payload_round_trip():
    from src.gateway.channels.message_bus import InboundMessage, InboundMessageType

    original = InboundMessage(
        channel_name="qq",
        chat_id="g123",
        user_id="u456",
        text="hello",
        msg_type=InboundMessageType.COMMAND,
        thread_ts=None,
        topic_id="t-1",
        files=[{"name": "x.txt"}],
        metadata={"k": "v"},
    )
    payload = _to_payload(original)
    rebuilt = _from_payload(payload)
    assert rebuilt.channel_name == original.channel_name
    assert rebuilt.chat_id == original.chat_id
    assert rebuilt.text == original.text
    assert rebuilt.msg_type == InboundMessageType.COMMAND
    assert rebuilt.topic_id == "t-1"
    assert rebuilt.files == [{"name": "x.txt"}]
    assert rebuilt.metadata == {"k": "v"}


def test_init_and_start_noop_when_disabled():
    from src.harness.dispatcher.lifespan import (
        init_dispatcher,
        shutdown_dispatcher,
        start_dispatcher_task,
        stop_dispatcher_task,
    )

    class _State:
        pass

    class _App:
        state = _State()

    app = _App()

    async def _go():
        assert await init_dispatcher() is False
        await start_dispatcher_task(app)
        await stop_dispatcher_task(app)
        await shutdown_dispatcher()

    asyncio.run(_go())


def test_dispatch_loop_disabled_does_not_start():
    from src.harness.dispatcher.dispatch import DispatchLoop, register_handler

    async def _h(_row):
        pass

    register_handler("test_kind", _h)

    async def _go():
        loop = DispatchLoop()
        loop.start()
        assert loop._task is None
        await loop.stop()

    asyncio.run(_go())
