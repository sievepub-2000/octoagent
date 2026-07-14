from langchain_core.tools import tool

from src.tools.permissions import apply_runtime_permission_policy, set_tool_permission_metadata


@tool("sandbox_probe")
def _sandbox_probe() -> str:
    """Read sandbox state."""
    return "ok"


@tool("directory_probe")
def _directory_probe() -> str:
    """Mutate the active project directory."""
    return "ok"


@tool("system_probe")
def _system_probe() -> str:
    """Mutate host state."""
    return "ok"


def _tools():
    return [
        set_tool_permission_metadata(_sandbox_probe, "sandbox", source="test"),
        set_tool_permission_metadata(_directory_probe, "directory", source="test"),
        set_tool_permission_metadata(_system_probe, "system", source="test"),
    ]


def test_permission_modes_expose_and_gate_expected_scopes() -> None:
    approval = {tool.name: tool.metadata for tool in apply_runtime_permission_policy(_tools(), "approval")}
    directory = {tool.name: tool.metadata for tool in apply_runtime_permission_policy(_tools(), "directory")}
    system = {tool.name: tool.metadata for tool in apply_runtime_permission_policy(_tools(), "system")}

    assert set(approval) == {"sandbox_probe", "directory_probe"}
    assert approval["directory_probe"]["requires_confirmation"] is True
    assert set(directory) == {"sandbox_probe", "directory_probe"}
    assert directory["directory_probe"]["requires_confirmation"] is False
    assert set(system) == {"sandbox_probe", "directory_probe", "system_probe"}
    assert system["system_probe"]["requires_confirmation"] is False
