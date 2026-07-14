from __future__ import annotations

from types import SimpleNamespace

from langchain_core.tools import tool
from langgraph.types import Command

from src.agents.middlewares.dangerous_tool_confirmation_middleware import DangerousToolConfirmationMiddleware, _signature


@tool("host_shell")
def _host_shell(command: str) -> str:
    """Run command."""

    return command


def _request(messages=None, runtime=None, metadata=None, command="systemctl restart octoagent-local.service"):
    _host_shell.metadata = metadata or {"permission_scope": "system", "requires_confirmation": True}
    return SimpleNamespace(
        tool=_host_shell,
        tool_call={"name": "host_shell", "id": "call-1", "args": {"command": command}},
        state={"messages": messages or [], "runtime": runtime or {}},
    )


def _pending_runtime(human_count: int = 1):
    args = {"command": "systemctl restart octoagent-local.service"}
    return {
        "dangerous_tool_pending": {
            "tool_name": "host_shell",
            "signature": _signature("host_shell", args),
            "args": args,
            "human_count": human_count,
        }
    }


def test_dangerous_tool_requires_confirmation() -> None:
    middleware = DangerousToolConfirmationMiddleware()

    blocked = middleware._maybe_block(_request())

    assert isinstance(blocked, Command)
    assert "任务已暂停" in blocked.update["messages"][0].content
    assert "1. 确认" in blocked.update["messages"][0].content
    assert "2. 取消" in blocked.update["messages"][0].content
    assert blocked.update["messages"][0].name == "ask_clarification"


def test_initial_user_confirmation_words_do_not_preapprove_tool() -> None:
    middleware = DangerousToolConfirmationMiddleware()
    human = SimpleNamespace(type="human", content="确认，继续执行")

    blocked = middleware._maybe_block(_request(messages=[human]))

    assert isinstance(blocked, Command)


def test_dangerous_tool_allows_after_user_confirmation() -> None:
    middleware = DangerousToolConfirmationMiddleware()
    initial_human = SimpleNamespace(type="human", content="重启服务")
    confirmation_human = SimpleNamespace(type="human", content="1")

    blocked = middleware._maybe_block(_request(messages=[initial_human, confirmation_human], runtime=_pending_runtime()))

    assert blocked is None


def test_dangerous_tool_cancels_after_user_denial() -> None:
    middleware = DangerousToolConfirmationMiddleware()
    initial_human = SimpleNamespace(type="human", content="重启服务")
    denial_human = SimpleNamespace(type="human", content="2")

    blocked = middleware._maybe_block(_request(messages=[initial_human, denial_human], runtime=_pending_runtime()))

    assert isinstance(blocked, Command)
    assert "已取消" in blocked.update["messages"][0].content


def test_pending_confirmation_blocks_other_tool_execution() -> None:
    middleware = DangerousToolConfirmationMiddleware()
    initial_human = SimpleNamespace(type="human", content="重启服务")

    blocked = middleware._maybe_block(
        _request(
            messages=[initial_human],
            runtime=_pending_runtime(),
            command="systemctl status octoagent-local.service",
        )
    )

    assert isinstance(blocked, Command)
    assert "任务已暂停" in blocked.update["messages"][0].content


def test_system_permission_mode_does_not_prompt_for_system_tool() -> None:
    middleware = DangerousToolConfirmationMiddleware()

    blocked = middleware._maybe_block(_request(metadata={"permission_scope": "system", "requires_confirmation": False, "active_permission_mode": "system"}))

    assert blocked is None


def test_duplicate_confirmation_not_reemitted_when_already_visible() -> None:
    from src.agents.middlewares.dangerous_tool_confirmation_middleware import _MARKER

    middleware = DangerousToolConfirmationMiddleware()
    initial_human = SimpleNamespace(type="human", content="重启服务")
    args = {"command": "systemctl restart octoagent-local.service"}
    sig = _signature("host_shell", args)
    prior = SimpleNamespace(
        type="tool",
        content=f'{_MARKER} tool="host_shell" signature="{sig}">\n请只回复 1/2\n</dangerous_tool_confirmation>',
    )

    blocked = middleware._maybe_block(_request(messages=[initial_human, prior], runtime=_pending_runtime()))

    assert isinstance(blocked, Command)
    # No duplicate confirmation message is emitted while the same prompt is visible.
    assert blocked.update.get("messages") is None


def test_new_confirmation_still_emitted_after_human_reply() -> None:
    from src.agents.middlewares.dangerous_tool_confirmation_middleware import _MARKER

    middleware = DangerousToolConfirmationMiddleware()
    args = {"command": "systemctl restart octoagent-local.service"}
    sig = _signature("host_shell", args)
    prior = SimpleNamespace(
        type="tool",
        content=f'{_MARKER} tool="host_shell" signature="{sig}">\n</dangerous_tool_confirmation>',
    )
    later_human = SimpleNamespace(type="human", content="再说一次")

    blocked = middleware._maybe_block(_request(messages=[prior, later_human]))

    # A human spoke after the prior prompt -> fail-open: a fresh prompt is emitted.
    assert isinstance(blocked, Command)
    assert blocked.update.get("messages")


def test_parallel_dangerous_calls_emit_single_prompt() -> None:
    """Two dangerous calls in one node pass share a messages list; only the first prompts."""
    middleware = DangerousToolConfirmationMiddleware()
    shared_messages = [SimpleNamespace(type="human", content="reboot services")]
    first = _request(messages=shared_messages, command="systemctl restart octoagent-local.service")
    second = _request(messages=shared_messages, command="systemctl restart nginx.service")

    blocked_first = middleware._maybe_block(first)
    blocked_second = middleware._maybe_block(second)

    assert isinstance(blocked_first, Command)
    assert (blocked_first.update or {}).get("messages")
    assert isinstance(blocked_second, Command)
    assert not (blocked_second.update or {}).get("messages")


def test_parallel_guard_does_not_suppress_new_messages_list() -> None:
    """A genuinely new node pass (distinct messages list) is never suppressed."""
    middleware = DangerousToolConfirmationMiddleware()
    first = _request(messages=[SimpleNamespace(type="human", content="reboot")], command="systemctl restart a.service")
    second = _request(messages=[SimpleNamespace(type="human", content="reboot")], command="systemctl restart b.service")

    assert (middleware._maybe_block(first).update or {}).get("messages")
    assert (middleware._maybe_block(second).update or {}).get("messages")
