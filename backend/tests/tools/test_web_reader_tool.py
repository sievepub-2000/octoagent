from __future__ import annotations

import json
from importlib import import_module

from src.tools.builtins import web_read_tool
from src.tools.builtins.web_read_tool import (
    _cap_extracted_content,
    _clean_extracted_text,
    _quality_failure_reason,
)


def test_web_read_extracts_article_without_browser(monkeypatch) -> None:
    web_read_module = import_module("src.tools.builtins.web_read_tool")

    monkeypatch.setattr(web_read_module, "is_url_safe", lambda _url: True)
    monkeypatch.setattr(web_read_module, "_timeout", lambda: 10.0)
    monkeypatch.setattr(
        web_read_module,
        "_fetch",
        lambda _url, timeout: (
            200,
            "text/html",
            "<html><head><title>Example</title></head><body><article><h1>Example</h1><p>" + "Useful article text. " * 30 + "</p></article></body></html>",
            "https://example.com/article",
        ),
    )

    result = web_read_tool.invoke({"url": "https://example.com/article"})

    assert "Useful article text" in result
    assert "browser_required" not in result


def test_web_read_explicitly_escalates_blocked_pages(monkeypatch) -> None:
    web_read_module = import_module("src.tools.builtins.web_read_tool")

    monkeypatch.setattr(web_read_module, "is_url_safe", lambda _url: True)
    monkeypatch.setattr(web_read_module, "_timeout", lambda: 10.0)
    monkeypatch.setattr(web_read_module, "_fetch", lambda _url, timeout: (403, "text/html", "Access denied", _url))

    payload = json.loads(web_read_tool.invoke({"url": "https://example.com/protected"}))

    assert payload["status"] == "browser_required"
    assert payload["next_tool"] == "browser"


def test_github_boilerplate_is_removed_from_extracted_text() -> None:
    raw = """
# Project README

Sponsor open source projects you depend on
Contributors are working behind the scenes to make open source better for everyone—give them the help and recognition they deserve.
Explore sponsorable projects
ProTip! Press the / key to activate the search input again and adjust your query.
{"resolvedServerColorMode":"day"}
You can’t perform that action at this time.

Actual project content that should remain.
"""

    cleaned = _clean_extracted_text("https://github.com/example/project", raw)

    assert "Actual project content that should remain." in cleaned
    assert "Sponsor open source projects" not in cleaned
    assert "ProTip!" not in cleaned
    assert "resolvedServerColorMode" not in cleaned
    assert "You can’t perform that action" not in cleaned


def test_non_github_content_is_not_domain_filtered() -> None:
    raw = "Sponsor open source projects you depend on\nActual content"

    cleaned = _clean_extracted_text("https://example.com/article", raw)

    assert cleaned == raw


def test_extracted_content_is_capped_with_actionable_note() -> None:
    capped = _cap_extracted_content("x" * 30_000)

    assert len(capped) < 25_000
    assert "content shortened" in capped


def test_low_quality_github_page_chrome_is_rejected() -> None:
    reason = _quality_failure_reason(
        "https://github.com/example/project",
        ("# GitHub\n\nSource: https://github.com/example/project\n\nSign in to GitHub. Navigation Menu. Repository page shell text repeated many times without useful project content or source files. " * 4),
        original_html="Sponsor open source projects you depend on resolvedServerColorMode",
    )

    assert reason is not None
    assert "navigation or login chrome" in reason
