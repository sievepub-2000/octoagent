from __future__ import annotations

import asyncio

import pytest

from src.gateway.routers import tools_registry


@pytest.mark.asyncio
async def test_tool_registry_builds_outside_the_event_loop(monkeypatch) -> None:
    built_on_worker = False
    expected = object()

    class FakeToolRegistryService:
        def build_registry(self):
            nonlocal built_on_worker
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                built_on_worker = True
            return expected

    monkeypatch.setattr(tools_registry, "ToolRegistryService", FakeToolRegistryService)

    result = await tools_registry.get_tool_capability_registry()

    assert result is expected
    assert built_on_worker is True
