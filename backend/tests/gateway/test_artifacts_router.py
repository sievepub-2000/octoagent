from __future__ import annotations

from pathlib import Path

from src.gateway.routers.artifacts import is_text_file_by_content


def test_content_probe_accepts_utf8_and_rejects_binary(tmp_path: Path) -> None:
    text = tmp_path / "artifact.unknown"
    binary = tmp_path / "artifact.pdf"
    text.write_text("OctoAgent 文本", encoding="utf-8")
    binary.write_bytes(b"%PDF-1.7\n\xe2\xe3\xcf\xd3\n")

    assert is_text_file_by_content(text) is True
    assert is_text_file_by_content(binary) is False
