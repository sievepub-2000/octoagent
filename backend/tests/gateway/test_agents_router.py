import inspect

from src.gateway.routers.agents import (
    check_agent_name,
    create_agent_endpoint,
    delete_agent,
    get_agent,
    update_agent,
)


def test_agent_file_mutations_run_in_fastapi_worker_pool() -> None:
    assert not inspect.iscoroutinefunction(create_agent_endpoint)
    assert not inspect.iscoroutinefunction(update_agent)
    assert not inspect.iscoroutinefunction(delete_agent)
    assert not inspect.iscoroutinefunction(check_agent_name)
    assert not inspect.iscoroutinefunction(get_agent)
