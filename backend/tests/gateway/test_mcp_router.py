import inspect

from src.gateway.routers.mcp import (
    delete_mcp_server,
    run_mcp_smoke_results,
    update_mcp_configuration,
    upsert_mcp_server,
)


def test_mcp_file_mutations_run_in_fastapi_worker_pool() -> None:
    assert not inspect.iscoroutinefunction(update_mcp_configuration)
    assert not inspect.iscoroutinefunction(upsert_mcp_server)
    assert not inspect.iscoroutinefunction(delete_mcp_server)


def test_mcp_smoke_test_remains_async() -> None:
    assert inspect.iscoroutinefunction(run_mcp_smoke_results)
