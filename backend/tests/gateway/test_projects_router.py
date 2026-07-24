from __future__ import annotations

import asyncio

from src.gateway.routers import projects


def test_project_service_initializes_outside_event_loop(monkeypatch) -> None:
    initialized_on_worker = False

    class FakeService:
        def list_projects(self, *, include_archived: bool) -> list[dict]:
            return [{"include_archived": include_archived}]

    def fake_service() -> FakeService:
        nonlocal initialized_on_worker
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            initialized_on_worker = True
        return FakeService()

    monkeypatch.setattr(projects, "get_project_service", fake_service)
    result = asyncio.run(projects.list_projects(include_archived=True))

    assert result == [{"include_archived": True}]
    assert initialized_on_worker is True
