from __future__ import annotations

import json

import pytest

from src.tools.capability_tools import list_capabilities_tool


def test_list_capabilities_accepts_null_kind() -> None:
    parsed = list_capabilities_tool.args_schema.model_validate({"kind": None})

    assert parsed.kind is None


def test_list_capabilities_treats_empty_kind_as_unfiltered() -> None:
    result = list_capabilities_tool.invoke({"kind": "", "max_items": 1})
    payload = json.loads(result)

    assert payload["returned"] >= 0


def test_list_capabilities_reports_unknown_kind_after_schema_parse() -> None:
    with pytest.raises(ValueError, match="Unsupported capability kind"):
        list_capabilities_tool.invoke({"kind": "unknown-kind"})
