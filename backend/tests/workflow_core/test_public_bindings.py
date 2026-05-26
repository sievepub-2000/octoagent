from __future__ import annotations

from types import SimpleNamespace

from src.storage.workflow.service import WorkflowCoreService


class _FakeDelegate:
    def __init__(self) -> None:
        self.workspace = SimpleNamespace(metadata={"existing": "kept"})
        self.merged: dict[str, object] | None = None

    def get_workspace(self, task_id: str):
        if task_id != "task-1":
            return None
        return self.workspace

    def merge_workspace_metadata(self, task_id: str, **metadata):
        if task_id != "task-1":
            return None
        self.merged = metadata
        self.workspace.metadata = metadata
        return self.workspace


def test_update_public_bindings_uses_delegate_metadata_merge() -> None:
    delegate = _FakeDelegate()
    service = WorkflowCoreService(delegate)  # type: ignore[arg-type]
    service.get_public_bindings = lambda task_id: {"workflow_id": task_id, "ok": True}  # type: ignore[method-assign]

    result = service.update_public_bindings(
        "task-1",
        channels=["slack", ""],
        mcp_servers=["voltagent"],
        skills=["deep-research"],
        plugins=["compound-engineering-review"],
    )

    assert result == {"workflow_id": "task-1", "ok": True}
    assert delegate.merged is not None
    assert delegate.merged["existing"] == "kept"
    assert delegate.merged["channel_bindings"] == [{"kind": "slack", "label": "slack", "enabled": True, "status": "enabled"}]
    assert delegate.merged["bound_mcp_servers"] == ["voltagent"]
    assert delegate.merged["enabled_skills"] == ["deep-research"]
    assert delegate.merged["active_plugin_ids"] == ["compound-engineering-review"]
