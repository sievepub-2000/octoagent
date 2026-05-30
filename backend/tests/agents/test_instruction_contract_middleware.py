from __future__ import annotations

from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.agents.middlewares.instruction_contract_middleware import _repair_response_for_instruction_contract


def test_current_research_replaces_local_exploration_with_source_first_web_search() -> None:
    response = ModelResponse(
        result=[
            AIMessage(
                content="",
                tool_calls=[{"id": "bad-local-call", "name": "bash", "args": {"command": "ls -la src"}}],
            )
        ],
        structured_response=None,
    )
    messages = [
        SystemMessage(
            content=(
                "<instruction_contract>\n"
                "- Intent: current_research\n"
                "- Required tool categories: web\n"
                "- User-named source domains to try first: bloomberg.com\n"
                "</instruction_contract>"
            )
        ),
        HumanMessage(content="Find Bloomberg's top ten news stories today and summarize details."),
    ]

    repaired = _repair_response_for_instruction_contract(response, messages, {})

    tool_call = repaired.result[0].tool_calls[0]
    assert tool_call["name"] == "web_search"
    assert tool_call["args"]["query"].startswith("site:bloomberg.com ")
    assert "Bloomberg" in tool_call["args"]["query"]


def test_current_research_explicit_url_uses_fetch_before_generic_search() -> None:
    response = ModelResponse(
        result=[AIMessage(content="", tool_calls=[{"id": "bad", "name": "read_file", "args": {"path": "README.md"}}])],
        structured_response=None,
    )
    messages = [
        SystemMessage(
            content=(
                "<instruction_contract>\n"
                "- Intent: current_research\n"
                "- Required tool categories: web\n"
                "</instruction_contract>"
            )
        ),
        HumanMessage(content="Read https://example.com/report and tell me what changed."),
    ]

    repaired = _repair_response_for_instruction_contract(response, messages, {})

    tool_call = repaired.result[0].tool_calls[0]
    assert tool_call["name"] == "web_fetch"
    assert tool_call["args"]["url"] == "https://example.com/report"


def test_current_research_keeps_valid_web_tool_call() -> None:
    response = ModelResponse(
        result=[AIMessage(content="", tool_calls=[{"id": "good", "name": "web_search", "args": {"query": "site:bloomberg.com markets"}}])],
        structured_response=None,
    )
    messages = [
        SystemMessage(
            content=(
                "<instruction_contract>\n"
                "- Intent: current_research\n"
                "- Required tool categories: web\n"
                "- User-named source domains to try first: bloomberg.com\n"
                "</instruction_contract>"
            )
        ),
        HumanMessage(content="Find current Bloomberg market news."),
    ]

    repaired = _repair_response_for_instruction_contract(response, messages, {})

    assert repaired is response
