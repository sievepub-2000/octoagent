from pathlib import Path

from src.agents.middlewares.state_middleware import StateMiddleware


def test_project_root_replaces_only_thread_workspace(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    middleware = StateMiddleware(base_dir=str(tmp_path / "runtime"), project_root_path=str(project_root))

    thread_data = middleware._thread_data_update("thread-1")["thread_data"]

    assert thread_data["workspace_path"] == str(project_root.resolve())
    assert thread_data["uploads_path"].endswith("threads/thread-1/uploads")
    assert thread_data["outputs_path"].endswith("threads/thread-1/outputs")


def test_thread_id_falls_back_to_run_config(monkeypatch) -> None:
    class RuntimeStub:
        context = {}

    monkeypatch.setattr(
        "src.agents.middlewares.state_middleware.get_config",
        lambda: {"configurable": {"thread_id": "thread-from-config"}},
    )

    assert StateMiddleware._thread_id(RuntimeStub()) == "thread-from-config"
