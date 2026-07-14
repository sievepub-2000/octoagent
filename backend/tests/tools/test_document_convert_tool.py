from __future__ import annotations

from pathlib import Path

from src.tools.builtins.document_convert_tool import convert_document_tool


def test_convert_document_converts_markdown_to_html(tmp_path: Path) -> None:
    markdown_file = tmp_path / "sample.md"
    markdown_file.write_text(
        "# Title\n\n| A | B |\n|---|---|\n| 1 | 2 |\n",
        encoding="utf-8",
    )

    result = convert_document_tool.func(None, str(markdown_file), "html", "tool-call-test")
    html_file = tmp_path / "sample.html"
    html = html_file.read_text(encoding="utf-8")

    assert "Converted sample.md" in result.update["messages"][0].content
    assert "sample.html" in result.update["messages"][0].content
    assert '<h1 id="title">Title</h1>' in html
    assert "<table>" in html
