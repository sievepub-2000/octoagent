from __future__ import annotations

import json
from importlib import import_module

from src.tools.builtins import browser_tool


def test_browser_tool_exposes_patchright_error_as_structured_result(monkeypatch) -> None:
    module = import_module("src.tools.builtins.browser_tool")

    monkeypatch.setattr(module, "_run_browser_call", lambda call: call())
    monkeypatch.setattr(module, "_run_browser", lambda *_args: (_ for _ in ()).throw(RuntimeError("unavailable")))

    payload = json.loads(browser_tool.invoke({"url": "https://example.com"}))

    assert payload == {"status": "error", "engine": "patchright", "error": "unavailable"}


def test_browser_tool_schema_accepts_ordered_actions() -> None:
    parsed = browser_tool.args_schema.model_validate(
        {
            "url": "https://example.com",
            "actions": [
                {"action": "fill", "target": "input[name=q]", "value": "OctoAgent"},
                {"action": "click", "target": "button[type=submit]"},
            ],
        }
    )

    assert len(parsed.actions) == 2
