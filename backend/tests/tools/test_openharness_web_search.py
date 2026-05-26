from __future__ import annotations

from src.tools.builtins.openharness_compat_tools import (
    _build_search_query_candidates,
    _satisfies_source_constraint,
    _score_search_result,
)


def test_official_source_constraint_does_not_require_known_fund_domain() -> None:
    query = "美国基金回报率前三 分红 增长率 只从官方网站获取信息"
    item = {
        "title": "Example Funds ABC Fund official total return and dividend data",
        "href": "https://example-funds.com/funds/abc",
        "snippet": "Official website fund total return dividend distribution information.",
        "published": "",
    }

    assert _satisfies_source_constraint(item, query)
    assert _score_search_result(item, query, query) > 0


def test_official_source_constraint_rejects_discussion_fallback() -> None:
    query = "美国基金回报率前三 分红 增长率 只从官方网站获取信息"
    item = {
        "title": "Reddit discussion about top dividend funds",
        "href": "https://reddit.com/r/investing/comments/example",
        "snippet": "Forum discussion about funds and total return.",
        "published": "",
    }

    assert not _satisfies_source_constraint(item, query)


def test_fund_query_candidates_remain_domain_open() -> None:
    query = "美国所有基金回报率前三的基金 分红 增长率 只从官方网站获取信息"

    candidates = _build_search_query_candidates(query)

    assert any("official" in candidate.lower() for candidate in candidates)
    assert all("site:vanguard.com" not in candidate.lower() for candidate in candidates)
    assert all("site:fidelity.com" not in candidate.lower() for candidate in candidates)
