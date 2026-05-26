from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from src.tools.builtins import system_ops_tools
from src.tools.builtins.system_ops_tools import (
    SYSTEM_OPS_TOOLS,
    config_drift_check_tool,
    config_drift_snapshot_tool,
    flipbook_tool,
    html_to_canvas_tool,
    media_probe_tool,
    python_package_install_tool,
    runtime_health_report_tool,
    security_audit_scan_tool,
)


def test_security_audit_scan_masks_secret_values(tmp_path: Path) -> None:
    secret_file = tmp_path / "config.env"
    fake_google_key = "AIza" + ("A" * 35)
    secret_file.write_text(f"GOOGLE_API_KEY={fake_google_key}\n", encoding="utf-8")

    result = security_audit_scan_tool.invoke({"root": str(tmp_path), "max_files": 5})
    payload = json.loads(result)

    assert payload["findings"]
    assert fake_google_key not in result
    assert payload["findings"][0]["masked_sample"].startswith("AIza")


def test_config_drift_check_detects_changed_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("value: 1\n", encoding="utf-8")
    snapshot = config_drift_snapshot_tool.invoke({"root": str(tmp_path), "include_globs": "config.yaml"})

    config_file.write_text("value: 2\n", encoding="utf-8")
    result = config_drift_check_tool.invoke({"snapshot_json": snapshot, "root": str(tmp_path)})
    payload = json.loads(result)

    assert payload["drift_detected"] is True
    assert any(path.endswith("config.yaml") for path in payload["changed"])


def test_media_probe_reads_image_metadata(tmp_path: Path) -> None:
    image_file = tmp_path / "sample.png"
    Image.new("RGB", (4, 3), color="red").save(image_file)

    result = media_probe_tool.invoke({"path": str(image_file)})
    payload = json.loads(result)

    assert payload["image"]["width"] == 4
    assert payload["image"]["height"] == 3


def test_canvas_and_flipbook_tools_are_registered() -> None:
    names = {tool.name for tool in SYSTEM_OPS_TOOLS}

    assert html_to_canvas_tool.name in names
    assert flipbook_tool.name in names


def test_artifact_dir_treats_null_output_name_as_auto_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(system_ops_tools, "_SYSTEM_TOOL_ARTIFACT_ROOT", tmp_path)

    artifact_dir = system_ops_tools._artifact_dir("html_to_canvas", "null")

    assert artifact_dir.parent == tmp_path / "html_to_canvas"
    assert artifact_dir.name.startswith("html_to_canvas-")


def test_flipbook_generates_html_artifact(tmp_path: Path) -> None:
    image_file = tmp_path / "frame.png"
    Image.new("RGB", (8, 6), color="blue").save(image_file)

    result = flipbook_tool.invoke({"frames_json": json.dumps([str(image_file)]), "output_name": "pytest-flipbook"})
    payload = json.loads(result)

    assert payload["tool"] == "flipbook"
    assert payload["frame_count"] == 1
    assert Path(payload["artifact"]).exists()
    assert Path(payload["frames_dir"], "frame-0001.png").exists()
    shutil.rmtree(Path(payload["artifact"]).parent, ignore_errors=True)


def test_runtime_health_report_returns_expected_sections() -> None:
    result = runtime_health_report_tool.invoke({"max_processes": 1})
    payload = json.loads(result)

    assert payload["version"]
    assert payload["memory"]["total"] > 0
    assert "git" in payload


def test_python_package_install_requires_user_confirmation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(system_ops_tools, "_SYSTEM_TOOL_ARTIFACT_ROOT", tmp_path)

    def fail_run(*_args, **_kwargs):
        raise AssertionError("pip must not run before user confirmation")

    monkeypatch.setattr(system_ops_tools.subprocess, "run", fail_run)

    result = python_package_install_tool.invoke({"packages": "example-package", "target_tool": "demo-tool"})
    payload = json.loads(result)

    assert payload["error"] == "user_confirmation_required"
    assert payload["default_install_root"].endswith("demo-tool")


def test_python_package_install_defaults_to_tool_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(system_ops_tools, "_SYSTEM_TOOL_ARTIFACT_ROOT", tmp_path)
    tool_python = tmp_path / "demo-tool" / ".venv" / "bin" / "python"
    calls = []

    def fake_ensure_tool_python_env(tool_name: str) -> Path:
        assert tool_name == "demo-tool"
        tool_python.parent.mkdir(parents=True, exist_ok=True)
        tool_python.write_text("", encoding="utf-8")
        return tool_python

    class FakeResult:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return FakeResult()

    monkeypatch.setattr(system_ops_tools, "_ensure_tool_python_env", fake_ensure_tool_python_env)
    monkeypatch.setattr(system_ops_tools.subprocess, "run", fake_run)

    result = python_package_install_tool.invoke(
        {
            "packages": "example-package",
            "target_tool": "demo-tool",
            "confirmed_by_user": True,
            "verification_command": "python --version",
        }
    )
    payload = json.loads(result)

    assert payload["exit_code"] == 0
    assert payload["install_scope"] == "tool_directory"
    assert payload["install_root"].endswith("demo-tool")
    assert calls[0][0][:4] == [str(tool_python), "-m", "pip", "install"]
    assert calls[1][0] == ["python", "--version"]
