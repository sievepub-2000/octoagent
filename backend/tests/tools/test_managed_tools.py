from __future__ import annotations

from pathlib import Path

import pytest

from src.tools.managed_tools import list_managed_tools, register_managed_tool, tool_root, uninstall_managed_tool


def test_managed_tool_lifecycle_is_manifest_backed(tmp_path: Path) -> None:
    entrypoint = tmp_path / "demo" / "source" / "demo.py"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text("print('ok')\n", encoding="utf-8")
    register_managed_tool(
        "demo",
        root=tmp_path,
        source_type="github",
        source="https://github.com/example/demo",
        version="v1.0.0",
        entrypoint="source/demo.py",
        invocation="python source/demo.py",
    )

    items = list_managed_tools(root=tmp_path)
    assert len(items) == 1
    assert items[0]["name"] == "demo"
    assert items[0]["callable"] is True

    result = uninstall_managed_tool("demo", root=tmp_path)
    assert result["ok"] is True
    assert result["post_delete_visible"] is False
    assert list_managed_tools(root=tmp_path) == []


def test_uninstall_refuses_unowned_directory(tmp_path: Path) -> None:
    unowned = tmp_path / "unowned"
    unowned.mkdir()
    (unowned / "keep.txt").write_text("keep", encoding="utf-8")

    result = uninstall_managed_tool("unowned", root=tmp_path)

    assert result["ok"] is False
    assert (unowned / "keep.txt").exists()


@pytest.mark.parametrize("name", ["../escape", "bad/name", "", "a" * 81])
def test_managed_tool_name_cannot_escape_root(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        tool_root(name, root=tmp_path)
