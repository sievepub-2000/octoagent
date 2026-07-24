import inspect

from src.gateway.routers.plugins import (
    disable_plugin,
    enable_plugin,
    install_plugin,
    list_plugin_capabilities,
    list_plugin_manifests,
    list_plugin_registry,
    recommend_plugins,
    uninstall_plugin,
)


def test_plugin_registry_operations_run_in_fastapi_worker_pool() -> None:
    handlers = (
        list_plugin_capabilities,
        list_plugin_manifests,
        list_plugin_registry,
        recommend_plugins,
        install_plugin,
        enable_plugin,
        disable_plugin,
        uninstall_plugin,
    )
    assert all(not inspect.iscoroutinefunction(handler) for handler in handlers)
