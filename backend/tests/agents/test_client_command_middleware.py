from __future__ import annotations

from src.agents.middlewares.client_command_middleware import _is_system_tools_inventory_request


def test_system_tools_inventory_request_allows_snapshot() -> None:
    assert _is_system_tools_inventory_request("请列出当前系统工具清单和工具状态") is True
    assert _is_system_tools_inventory_request("What system tools are available?") is True


def test_system_tools_execution_request_does_not_use_inventory_snapshot() -> None:
    assert _is_system_tools_inventory_request("请通过 bash 系统工具执行 printf hello") is False
    assert _is_system_tools_inventory_request("检查并测试系统工具库里的所有工具是否正常使用") is False
    assert _is_system_tools_inventory_request("Please test the available tools by calling bash") is False
