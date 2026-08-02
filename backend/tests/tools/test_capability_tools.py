from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.tools.capability_tools import inspect_octoagent_runtime_tool, list_capabilities_tool
from src.tools.catalog import BUILTIN_TOOLS_CORE


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


def test_runtime_discovery_tools_are_always_visible() -> None:
    names = {tool.name for tool in BUILTIN_TOOLS_CORE}

    assert {"list_capabilities", "inspect_octoagent_runtime"} <= names


def test_list_capabilities_uses_harness_registry() -> None:
    payload = json.loads(list_capabilities_tool.invoke({"kind": "builtin_tool", "max_items": 1}))

    assert payload["source"] == "/api/harness"
    assert payload["summary"]["builtin_tools_total"] > 0
    assert payload["items"][0]["kind"] == "builtin_tool"


def test_harness_registry_does_not_hide_builtin_loading_failure() -> None:
    from src.tools.registry.service import ToolRegistryService

    class BrokenCatalog:
        def list_items(self):
            raise ImportError("broken configured tool")

    service = ToolRegistryService(
        extensions_config_getter=lambda: SimpleNamespace(mcp_servers={}),
        plugin_service_getter=lambda: SimpleNamespace(
            list_plugins=lambda: SimpleNamespace(plugins=[])
        ),
        skills_loader=lambda **_kwargs: [],
        app_config_getter=lambda: SimpleNamespace(models=[]),
        subagents_config_getter=lambda: SimpleNamespace(
            max_concurrent_subagents=0, max_total_subagent_jobs=0
        ),
        runtime_snapshot_getter=lambda: {},
        builtin_catalog=BrokenCatalog(),
        channel_reader=SimpleNamespace(read=lambda: []),
        managed_tools_loader=lambda: [],
    )

    with pytest.raises(ImportError, match="broken configured tool"):
        service.build_registry()


def test_list_capabilities_defaults_to_compact_queryable_results(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.tools import capability_tools

    items = [
        {
            "capability_id": f"builtin:tool_{index}",
            "kind": "builtin_tool",
            "name": f"tool_{index}",
            "display_name": f"Tool {index}",
            "description": "x" * 500,
            "enabled": True,
            "source": "/api/harness",
            "metadata": {"parameters": {"huge": "y" * 2_000}},
        }
        for index in range(40)
    ]
    monkeypatch.setattr(
        capability_tools,
        "_harness_items",
        lambda: ({"summary": {"harness_total": 40}, "runtime": {"status": "healthy"}}, items),
    )

    payload = json.loads(list_capabilities_tool.invoke({}))

    assert payload["returned"] == 20
    assert payload["truncated"] is True
    assert "metadata" not in payload["items"][0]
    assert len(payload["items"][0]["description"]) <= 240
    assert len(json.dumps(payload, ensure_ascii=False)) < 10_000


def test_list_capabilities_query_filters_before_limiting(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.tools import capability_tools

    items = [
        {"kind": "skill", "name": "document_writer", "description": "Create DOCX", "enabled": True, "source": "/api/harness", "metadata": {}},
        {"kind": "skill", "name": "image_editor", "description": "Edit PNG", "enabled": True, "source": "/api/harness", "metadata": {}},
    ]
    monkeypatch.setattr(
        capability_tools,
        "_harness_items",
        lambda: ({"summary": {"harness_total": 2}, "runtime": {}}, items),
    )

    payload = json.loads(list_capabilities_tool.invoke({"query": "DOCX"}))

    assert [item["name"] for item in payload["items"]] == ["document_writer"]


def test_runtime_inspection_is_sanitized_and_uses_authoritative_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.tools import capability_tools

    def fake_probe(name: str, url: str, *, expected_status: str | None = None):
        body = {"status": expected_status or "ok"}
        if name == "system_executor":
            body = {"status": "healthy", "token_ready": True, "docker_socket": True}
        return {"name": name, "url": url, "reachable": True, "http_status": 200, "body": body}

    monkeypatch.setattr(capability_tools, "_probe_json", fake_probe)
    payload = json.loads(inspect_octoagent_runtime_tool.invoke({}))
    serialized = json.dumps(payload)

    assert payload["authoritative_sources"]["harness"] == "/api/harness"
    assert payload["services"]["system_executor"]["reachable"] is True
    assert "api_key" not in serialized.lower()
    assert "authorization" not in serialized.lower()
