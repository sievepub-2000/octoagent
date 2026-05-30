from __future__ import annotations

from src.tools.builtins.web_reader_tool import (
    _cap_extracted_content,
    _clean_extracted_text,
    _is_recoverable_http_status,
    _quality_failure_reason,
)


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
    assert "content shortened by OctoAgent web reader" in capped


def test_low_quality_github_page_chrome_is_rejected() -> None:
    reason = _quality_failure_reason(
        "https://github.com/example/project",
        ("# GitHub\n\nSource: https://github.com/example/project\n\nSign in to GitHub. Navigation Menu. Repository page shell text repeated many times without useful project content or source files. " * 4),
        original_html="Sponsor open source projects you depend on resolvedServerColorMode",
    )

    assert reason is not None
    assert "boilerplate" in reason


def test_antibot_http_statuses_are_recoverable_by_web_fetch_chain() -> None:
    assert _is_recoverable_http_status(403)
    assert _is_recoverable_http_status(429)
    assert _is_recoverable_http_status(503)
    assert not _is_recoverable_http_status(404)
