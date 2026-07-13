import json
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

    context = service.resolve_execution_context(
        created["project_id"],
        requested_model="explicit-model",
        requested_permission="system",
    )
    assert context.root_path == str(root.resolve())
    assert context.model_name == "explicit-model"
    assert context.permission_mode == "directory"

    updated = service.update_project(created["project_id"], status="archived", pinned_files=["README.md"])
    assert updated is not None
    assert updated["pinned_files"] == ["README.md"]
    assert service.list_projects() == []
    assert len(service.list_projects(include_archived=True)) == 1


def test_project_rejects_missing_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.storage.project.service._ALLOWED_ROOTS", (tmp_path,))
    service = ProjectService(store_path=tmp_path / "projects.json")
    with pytest.raises(ValueError, match="does not exist"):
        service.create_project("Missing", str(tmp_path / "missing"))


def test_project_store_migrates_legacy_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr("src.storage.project.service._ALLOWED_ROOTS", (tmp_path,))
    legacy = tmp_path / "projects.json"
    legacy.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "project_id": "proj-legacy",
                        "name": "Legacy",
                        "root_path": str(root),
                        "created_at": "2026-07-13T00:00:00+00:00",
                        "updated_at": "2026-07-13T00:00:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    service = ProjectService(store_path=legacy)

    assert service.store_path.suffix == ".sqlite3"
    assert service.get_project("proj-legacy")["name"] == "Legacy"
