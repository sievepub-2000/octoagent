from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from zipfile import is_zipfile

import pytest


@pytest.mark.parametrize("format_name", ["docx", "xlsx", "pptx", "pdf", "md"])
def test_office_generation_creates_real_files(tmp_path: Path, format_name: str) -> None:
    script = Path(__file__).resolve().parents[3] / "skills" / "public" / "office-generation" / "scripts" / "generate.py"
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "title": "测试报告",
                "sections": [{"heading": "结论", "paragraphs": ["系统正常。"], "bullets": ["项目一"]}],
                "headers": ["名称", "状态"],
                "rows": [["OctoAgent", "正常"]],
                "slides": [{"title": "测试报告", "subtitle": "摘要"}, {"title": "结论", "bullets": ["系统正常"]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / f"report.{format_name}"

    result = subprocess.run(
        [sys.executable, str(script), "--format", format_name, "--spec", str(spec), "--output-file", str(output)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output.stat().st_size > 20
    if format_name in {"docx", "xlsx", "pptx"}:
        assert is_zipfile(output)
    elif format_name == "pdf":
        assert output.read_bytes().startswith(b"%PDF-")
    else:
        assert "系统正常" in output.read_text(encoding="utf-8")
