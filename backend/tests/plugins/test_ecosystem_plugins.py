from __future__ import annotations

from src.tools.capability_tools import get_plugin_command_tool
from src.tools.plugins import get_plugin_service


def test_ecosystem_plugins_are_registered() -> None:
    service = get_plugin_service()
    plugin_ids = {item.plugin_id for item in service.list_plugins().plugins}

    assert "goalbuddy-workflow" in plugin_ids
    assert "diagram-generation-toolkit" in plugin_ids
    assert "lumibot-research-strategy" in plugin_ids
    assert "ian-handdrawn-ppt" in plugin_ids


def test_plugin_command_resolves_integrated_workflow() -> None:
    result = get_plugin_command_tool.invoke({"command_id": "ian:blueprint"})

    assert "ian-handdrawn-ppt" in result
    assert "Create Handdrawn PPT Blueprint" in result
