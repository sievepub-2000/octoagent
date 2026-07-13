from pathlib import Path

import pytest

from src.storage.project.service import ProjectService


def test_project_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr("src.storage.project.service._ALLOWED_ROOTS", (tmp_path,))
    service = ProjectService(store_path=tmp_path / "projects.json")

    created = service.create_project("OctoAgent", str(root), instructions="Keep changes small")
    assert created["root_path"] == str(root.resolve())
    assert service.list_projects()[0]["project_id"] == created["project_id"]

    updated = service.update_project(created["project_id"], status="archived", pinned_files=["README.md"])
    assert updated is not None
    assert updated["pinned_files"] == ["README.md"]
    assert service.list_projects() == []
    assert len(service.list_projects(include_archived=True)) == 1

    assert service.delete_project(created["project_id"])
    assert not service.delete_project(created["project_id"])


def test_project_rejects_missing_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.storage.project.service._ALLOWED_ROOTS", (tmp_path,))
    service = ProjectService(store_path=tmp_path / "projects.json")
    with pytest.raises(ValueError, match="does not exist"):
        service.create_project("Missing", str(tmp_path / "missing"))
