from __future__ import annotations

import asyncio

from src.gateway.channels import service


def test_channel_service_construction_is_offloaded(monkeypatch) -> None:
    calls: list[object] = []

    class FakeService:
        async def start(self) -> None:
            return None

    fake_service = FakeService()

    async def fake_to_thread(function):
        calls.append(function)
        return function()

    monkeypatch.setattr(service, "_channel_service", None)
    monkeypatch.setattr(service.ChannelService, "from_app_config", lambda: fake_service)
    monkeypatch.setattr(service.asyncio, "to_thread", fake_to_thread)

    created = asyncio.run(service.start_channel_service())

    assert created is fake_service
    assert len(calls) == 1
    service._channel_service = None
