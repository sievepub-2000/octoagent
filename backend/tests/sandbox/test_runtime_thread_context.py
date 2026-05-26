from __future__ import annotations

from types import SimpleNamespace

from src.tools.sandbox.tools import get_runtime_thread_id, get_thread_data


def test_get_runtime_thread_id_falls_back_to_configurable_thread_id() -> None:
    runtime = SimpleNamespace(
        context={},
        config={"configurable": {"thread_id": "thread-from-config"}},
        state={},
    )

    assert get_runtime_thread_id(runtime) == "thread-from-config"
    assert runtime.context["thread_id"] == "thread-from-config"


def test_get_thread_data_lazily_builds_paths_from_config_thread_id() -> None:
    runtime = SimpleNamespace(
        context={},
        config={"configurable": {"thread_id": "thread-lazy-paths"}},
        state={},
    )

    thread_data = get_thread_data(runtime)

    assert thread_data is not None
    assert thread_data["workspace_path"].endswith("/thread-lazy-paths/workspace")
    assert thread_data["uploads_path"].endswith("/thread-lazy-paths/uploads")
    assert thread_data["outputs_path"].endswith("/thread-lazy-paths/outputs")
    assert runtime.state["thread_data"] == thread_data


def test_get_runtime_thread_id_falls_back_to_first_message_id() -> None:
    message = SimpleNamespace(id="msg-123", content="hello")
    runtime = SimpleNamespace(
        context={},
        config={},
        state={"messages": [message]},
    )

    assert get_runtime_thread_id(runtime) == "message-msg-123"
    assert runtime.context["thread_id"] == "message-msg-123"


def test_get_runtime_thread_id_falls_back_to_run_id() -> None:
    runtime = SimpleNamespace(
        context={},
        config={"run_id": "run-123"},
        state={},
    )

    assert get_runtime_thread_id(runtime) == "run-run-123"
    assert runtime.context["thread_id"] == "run-run-123"
