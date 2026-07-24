from __future__ import annotations

import inspect

from src.gateway.routers import skills


def test_filesystem_skill_mutations_use_fastapi_worker_pool() -> None:
    assert not inspect.iscoroutinefunction(skills.create_skill)
    assert not inspect.iscoroutinefunction(skills.update_skill)
    assert not inspect.iscoroutinefunction(skills.install_skill)
    assert not inspect.iscoroutinefunction(skills.delete_skill)


def test_network_skill_install_remains_async() -> None:
    assert inspect.iscoroutinefunction(skills.install_agency_agents)
