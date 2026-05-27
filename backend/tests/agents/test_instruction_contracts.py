from __future__ import annotations

from src.agents.core.instruction_contracts import build_contract_prompt, detect_instruction_contract


def test_named_source_research_starts_source_first_and_caps_evidence_links() -> None:
    contract = detect_instruction_contract("查询reddit前十大新闻，汇总报告")

    assert contract.intent == "current_research"
    assert contract.required_domains == ("reddit.com",)
    assert contract.min_evidence_links == 5

    prompt = build_contract_prompt(contract)
    assert "User-named source domains to try first: reddit.com" in prompt
    assert "source-scoped search" in prompt
    assert "broaden only after stating the source-specific gap" in prompt


def test_chinese_bloomberg_source_name_maps_to_source_domain() -> None:
    contract = detect_instruction_contract("查询彭博社前十大新闻")

    assert contract.required_domains == ("bloomberg.com",)
    assert contract.min_evidence_links == 5


def test_x_source_contract_does_not_require_ten_urls_for_top_ten() -> None:
    contract = detect_instruction_contract("查询x.com前十大热门新闻及详细内容")

    assert contract.required_domains == ("x.com",)
    assert contract.min_evidence_links == 5
