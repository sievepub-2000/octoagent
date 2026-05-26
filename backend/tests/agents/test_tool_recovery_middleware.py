from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from src.agents.middlewares.tool_budget_middleware import ToolBudgetMiddleware


class _Runtime:
    def __init__(self, context: dict) -> None:
        self.context = context


def _ai_tool_call(tool_name: str = "bash", call_id: str = "call-1", args: dict | None = None) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": tool_name, "args": args or {"command": "pwd"}, "id": call_id}],
    )


def _tool_error(tool_name: str = "bash", call_id: str = "call-1", content: str = "Error: failed") -> ToolMessage:
    return ToolMessage(content=content, name=tool_name, tool_call_id=call_id, status="error")


def test_successful_tool_messages_do_not_trigger_low_budget_finalization() -> None:
    middleware = ToolBudgetMiddleware()
    messages = [HumanMessage(content="inspect the workspace")]
    for index in range(20):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(call_id=call_id))
        messages.append(ToolMessage(content="ok", name="bash", tool_call_id=call_id))
    messages.append(_ai_tool_call(call_id="call-final"))
    state = {"messages": messages}

    assert middleware.after_model(state, None) is None


def test_missing_description_is_auto_filled_before_tool_execution() -> None:
    middleware = ToolBudgetMiddleware()
    request = ToolCallRequest(
        tool_call={"name": "bash", "args": {"command": "pwd"}, "id": "call-1"},
        tool=None,
        state={"messages": []},
        runtime=None,
    )

    def handler(next_request: ToolCallRequest) -> ToolMessage:
        assert next_request.tool_call["args"]["description"].startswith("Run command:")
        return ToolMessage(content="/workspace", name="bash", tool_call_id="call-1")

    result = middleware.wrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "success"


def test_tool_error_injects_recovery_guidance_before_next_model_call() -> None:
    middleware = ToolBudgetMiddleware()
    state = {
        "messages": [
            HumanMessage(content="run a command"),
            _ai_tool_call(call_id="call-1"),
            _tool_error(content="Error invoking tool 'bash': description: Field required"),
        ]
    }

    update = middleware.before_model(state, None)

    assert update is not None
    guidance = update["messages"][0].content
    assert "tool_recovery_policy" in guidance
    assert "修正参数" in guidance
    assert update["runtime"]["tool_recovery"]["stage"] == "repair"


def test_repeated_tool_errors_record_and_inject_memory_lessons(monkeypatch) -> None:
    class _Entry:
        def __init__(self, content: str, metadata: dict) -> None:
            self.content = content
            self.metadata = metadata

    class _Store:
        def __init__(self) -> None:
            self.added: list[tuple[str, str, dict]] = []

        def list_entries(self, *, namespace: str, limit: int):
            assert namespace == "skill_evolution"
            assert limit == 200
            return []

        def add(self, namespace: str, content: str, *, agent_name: str | None = None, metadata: dict | None = None) -> str:
            assert namespace == "skill_evolution"
            assert agent_name == "ToolBudgetMiddleware"
            self.added.append((namespace, content, metadata or {}))
            return "lesson-1"

        def search(self, query: str, *, namespace: str | None = None, top_k: int = 10):
            assert namespace == "skill_evolution"
            assert "tool recovery" in query
            return [
                _Entry(
                    "Historical lesson: after repeated bash failures, inspect settings and switch tools before asking the user for missing configuration.",
                    {"kind": "tool_recovery_lesson"},
                )
            ]

    store = _Store()
    monkeypatch.setattr("src.agents.memory.system_rag_store.get_system_rag_store", lambda: store)
    middleware = ToolBudgetMiddleware()
    messages = [HumanMessage(content="run command")]
    for index in range(3):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(call_id=call_id))
        messages.append(_tool_error(call_id=call_id, content="Error: command failed"))

    update = middleware.before_model({"messages": messages}, None)

    assert update is not None
    assert store.added
    namespace, content, metadata = store.added[0]
    assert namespace == "skill_evolution"
    assert "Experience summary" in content
    assert metadata["kind"] == "tool_recovery_lesson"
    assert metadata["stage"] == "alternate"
    guidance = update["messages"][0].content
    assert "tool_recovery_memory" in guidance
    assert "Historical lesson" in guidance
    assert update["runtime"]["tool_recovery"]["memory_lesson_recorded"] is True
    assert update["runtime"]["tool_recovery"]["memory_lessons_injected"] == 1


def test_repeated_same_tool_errors_are_blocked_with_switch_guidance() -> None:
    middleware = ToolBudgetMiddleware(switch_tool_errors=3)
    messages = [HumanMessage(content="run command")]
    for index in range(3):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(call_id=call_id))
        messages.append(_tool_error(call_id=call_id, content="Error: repeated failure"))
    request = ToolCallRequest(
        tool_call={"name": "bash", "args": {"command": "pwd"}, "id": "call-next"},
        tool=None,
        state={"messages": messages},
        runtime=None,
    )

    result = middleware.wrap_tool_call(request, lambda next_request: ToolMessage(content="should not run", tool_call_id="call-next"))

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "switching to a different tool" in result.content
    assert result.additional_kwargs["octo_tool_recovery_guard"] is True


def test_duplicate_guard_counts_actual_tool_calls_once() -> None:
    middleware = ToolBudgetMiddleware()
    messages = [HumanMessage(content="run command")]
    for index in range(2):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(call_id=call_id, args={"command": "pwd"}))
        messages.append(ToolMessage(content="/workspace", name="bash", tool_call_id=call_id))
    request = ToolCallRequest(
        tool_call={"name": "bash", "args": {"command": "pwd"}, "id": "call-next"},
        tool=None,
        state={"messages": messages},
        runtime=None,
    )

    result = middleware.wrap_tool_call(request, lambda next_request: ToolMessage(content="/workspace", name="bash", tool_call_id="call-next"))

    assert isinstance(result, ToolMessage)
    assert result.content == "/workspace"
    assert result.status == "success"


def test_duplicate_write_todos_is_nonfatal_planning_noop() -> None:
    middleware = ToolBudgetMiddleware()
    messages = [HumanMessage(content="research content subscription saas")]
    args = {"todos": [{"content": "research market", "status": "in_progress"}]}
    for index in range(4):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(tool_name="write_todos", call_id=call_id, args=args))
        messages.append(ToolMessage(content="updated", name="write_todos", tool_call_id=call_id))
    request = ToolCallRequest(
        tool_call={"name": "write_todos", "args": args, "id": "call-next"},
        tool=None,
        state={"messages": messages},
        runtime=None,
    )

    result = middleware.wrap_tool_call(
        request,
        lambda next_request: ToolMessage(content="should not run", name="write_todos", tool_call_id="call-next"),
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "success"
    assert result.name == "write_todos"
    assert result.additional_kwargs["octo_planning_noop_guard"] is True
    assert "Prefer not to call write_todos again" in result.content
    assert "web_search" in result.content


def test_repeated_write_todos_noop_loop_injects_memory_soft_constraint() -> None:
    middleware = ToolBudgetMiddleware()
    messages = [HumanMessage(content="research a company")]
    args = {"todos": [{"content": "research market", "status": "in_progress"}]}
    for index in range(8):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(tool_name="write_todos", call_id=call_id, args=args))
        messages.append(
            ToolMessage(
                content="Todo planning update skipped: duplicate write_todos.",
                name="write_todos",
                tool_call_id=call_id,
                additional_kwargs={"octo_planning_noop_guard": True},
            )
        )

    update = middleware.before_model({"messages": messages, "runtime": {}}, None)

    assert update is not None
    guidance = update["messages"][0].content
    assert "runtime_self_constraint_reflection" in guidance
    assert "planning_noop_loop" in guidance
    assert "search_memory" in guidance
    assert "archival_memory_insert" in guidance
    assert update["runtime"]["tool_recovery"]["stage"] == "planning_loop_soft_constraint"
    assert update["runtime"]["tool_recovery"]["hard_stop"] is False


def test_write_todos_duplicate_guards_do_not_trigger_final_failure_report() -> None:
    middleware = ToolBudgetMiddleware(final_failure_errors=9)
    messages = [HumanMessage(content="research content subscription saas")]
    args = {"todos": [{"content": "research market", "status": "in_progress"}]}
    for index in range(9):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(tool_name="write_todos", call_id=call_id, args=args))
        messages.append(
            ToolMessage(
                content="Error: this exact tool call (write_todos with identical arguments) has already been tried 8 times in this turn with the same result.",
                name="write_todos",
                tool_call_id=call_id,
                status="error",
            )
        )
    messages.append(_ai_tool_call(tool_name="write_todos", call_id="call-final", args=args))

    assert middleware.after_model({"messages": messages}, None) is None


def test_web_research_budget_injects_closure_guidance() -> None:
    middleware = ToolBudgetMiddleware()
    messages = [HumanMessage(content="research content subscription saas")]
    for index in range(6):
        call_id = f"fetch-{index}"
        messages.append(_ai_tool_call(tool_name="web_fetch", call_id=call_id, args={"url": f"https://example.com/{index}"}))
        messages.append(ToolMessage(content="# Source\n\n" + "useful evidence " * 30, name="web_fetch", tool_call_id=call_id))

    update = middleware.before_model({"messages": messages}, None)

    assert update is not None
    guidance = update["messages"][0].content
    assert "research_closure_policy" in guidance
    assert "Produce the final user-facing report now" in guidance
    assert update["runtime"]["research_closure"]["status"] == "must_finalize"


def test_web_research_budget_injects_closure_after_step_review_message() -> None:
    middleware = ToolBudgetMiddleware()
    messages = [HumanMessage(content="research content subscription saas")]
    for index in range(6):
        call_id = f"fetch-{index}"
        messages.append(_ai_tool_call(tool_name="web_fetch", call_id=call_id, args={"url": f"https://example.com/{index}"}))
        messages.append(ToolMessage(content="# Source\n\n" + "useful evidence " * 30, name="web_fetch", tool_call_id=call_id))
    messages.append(SystemMessage(content="step review message"))

    update = middleware.before_model({"messages": messages}, None)

    assert update is not None
    assert "research_closure_policy" in update["messages"][0].content
    assert update["runtime"]["research_closure"]["status"] == "must_finalize"


def test_web_research_budget_does_not_hard_block_more_fetches_by_default() -> None:
    middleware = ToolBudgetMiddleware()
    messages = [HumanMessage(content="research content subscription saas")]
    for index in range(6):
        call_id = f"fetch-{index}"
        messages.append(_ai_tool_call(tool_name="web_fetch", call_id=call_id, args={"url": f"https://example.com/{index}"}))
        messages.append(ToolMessage(content="# Source\n\n" + "useful evidence " * 30, name="web_fetch", tool_call_id=call_id))
    request = ToolCallRequest(
        tool_call={"name": "web_fetch", "args": {"url": "https://example.com/extra"}, "id": "fetch-next"},
        tool=None,
        state={"messages": messages},
        runtime=None,
    )

    result = middleware.wrap_tool_call(
        request,
        lambda next_request: ToolMessage(content="executed", name="web_fetch", tool_call_id="fetch-next"),
    )

    assert isinstance(result, ToolMessage)
    assert result.content == "executed"
    assert "octo_research_closure_guard" not in result.additional_kwargs


def test_research_closure_compacts_web_evidence_before_final_model_call() -> None:
    middleware = ToolBudgetMiddleware()
    messages = [HumanMessage(content="research content subscription saas")]
    for index in range(6):
        call_id = f"fetch-{index}"
        messages.append(_ai_tool_call(tool_name="web_fetch", call_id=call_id, args={"url": f"https://example.com/{index}"}))
        messages.append(
            ToolMessage(
                content="# Source\n\nhttps://example.com/source " + "very detailed evidence " * 200,
                name="web_fetch",
                tool_call_id=call_id,
            )
        )
    messages.append(
        ToolMessage(
            content="Research collection skipped: enough web evidence has already been gathered.",
            name="web_fetch",
            tool_call_id="fetch-next",
            additional_kwargs={"octo_research_closure_guard": True},
        )
    )

    update = middleware.before_model(
        {
            "messages": messages,
            "runtime": {"research_closure": {"status": "must_finalize"}},
        },
        None,
    )

    assert update is not None
    assert update["runtime"]["research_evidence_compaction"]["status"] == "compacted_for_final"
    compacted_tools = [message for message in update["messages"] if isinstance(message, ToolMessage)]
    assert any(message.additional_kwargs.get("octo_research_evidence_compacted") for message in compacted_tools)
    assert all(len(message.content) < 1800 for message in compacted_tools if message.name == "web_fetch")
    assert "research_final_answer_mode" in update["messages"][-1].content


def test_research_closure_compacts_even_after_closure_guidance_message() -> None:
    middleware = ToolBudgetMiddleware()
    messages = [HumanMessage(content="research content subscription saas")]
    for index in range(4):
        call_id = f"search-{index}"
        messages.append(_ai_tool_call(tool_name="web_search", call_id=call_id, args={"query": f"q{index}"}))
        messages.append(
            ToolMessage(
                content=(
                    f'{{"title":"Creator subscription platform report {index}",'
                    f'"url":"https://example.com/{index}"}} '
                    + "Substack Patreon membership content subscription " * 80
                ),
                name="web_search",
                tool_call_id=call_id,
            )
        )
    messages.append(SystemMessage(content="Web research has reached the evidence sufficiency threshold for this turn."))

    update = middleware.before_model(
        {
            "messages": messages,
            "runtime": {"research_closure": {"status": "must_finalize"}},
        },
        None,
    )

    assert update is not None
    assert update["runtime"]["research_evidence_compaction"]["status"] == "compacted_for_final"
    assert update["messages"][-1].type == "system"
    assert "research_final_answer_mode" in update["messages"][-1].content


def test_research_closure_uses_model_guided_soft_review_without_forced_answer() -> None:
    middleware = ToolBudgetMiddleware()
    messages = [HumanMessage(content="Research ANPZ tax, debt, operations, revenue, profit, and exports.")]
    for index in range(8):
        call_id = f"search-{index}"
        messages.append(_ai_tool_call(tool_name="web_search", call_id=call_id, args={"query": f"ANPZ evidence {index}"}))
        messages.append(
            ToolMessage(
                content=(
                    f"ANPZ Atyrau refinery official evidence {index} https://example.kz/anpz/{index} "
                    + "Atyrau Oil Refinery Kazakhstan revenue debt tax exports operations " * 20
                ),
                name="web_search",
                tool_call_id=call_id,
            )
        )
    messages.append(_ai_tool_call(tool_name="web_search", call_id="search-extra", args={"query": "more ANPZ evidence"}))

    update = middleware.after_model(
        {
            "messages": messages,
            "runtime": {"research_closure": {"status": "must_finalize"}},
        },
        None,
    )

    assert update is not None
    assert "messages" not in update
    assert update["runtime"]["research_closure"]["status"] == "must_finalize"
    assert update["runtime"]["research_closure"]["summary_mode"] == "model_guided"
    assert update["runtime"]["research_closure"]["soft_review_tool_calls"] == ["web_search"]
    assert update["runtime"]["self_feedback_action"] == "self_review_web_tools_after_research_closure"

    compacted = middleware.before_model(
        {
            "messages": messages,
            "runtime": update["runtime"],
        },
        None,
    )
    assert compacted is not None
    assert compacted["runtime"]["research_evidence_compaction"]["status"] == "compacted_for_final"

    soft = middleware.before_model(
        {
            "messages": compacted["messages"],
            "runtime": compacted["runtime"],
        },
        None,
    )

    assert soft is not None
    guidance = soft["messages"][0].content
    assert "runtime_self_constraint_reflection" in guidance
    assert "research_closure_loop" in guidance
    assert "search_memory" in guidance
    assert "archival_memory_insert" in guidance
    assert "Substack" not in guidance
    assert "Patreon" not in guidance


def test_recovery_guard_messages_do_not_escalate_error_budget() -> None:
    middleware = ToolBudgetMiddleware(switch_tool_errors=3, discover_tool_errors=6, final_failure_errors=9)
    messages = [HumanMessage(content="inspect host")]
    for index in range(3):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(tool_name="host_shell", call_id=call_id, args={"command": "bad-command"}))
        messages.append(_tool_error(tool_name="host_shell", call_id=call_id, content="Error: command failed"))
    for index in range(4):
        messages.append(
            ToolMessage(
                content="Error: tool 'host_shell' has already failed 3 times in this turn. Recovery policy requires switching to a different tool or implementation path.",
                name="host_shell",
                tool_call_id=f"guard-{index}",
                status="error",
            )
        )
    request = ToolCallRequest(
        tool_call={"name": "host_shell", "args": {"command": "bad-command"}, "id": "call-next"},
        tool=None,
        state={"messages": messages},
        runtime=None,
    )

    result = middleware.wrap_tool_call(request, lambda next_request: ToolMessage(content="should not run", tool_call_id="call-next"))

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "has already failed 3 times" in result.content
    assert "capability discovery" not in result.content
    assert "工具调用连续失败" not in result.content


def test_repeated_web_fetch_errors_require_different_source_guidance() -> None:
    middleware = ToolBudgetMiddleware(switch_tool_errors=3)
    messages = [HumanMessage(content="fetch this page")]
    for index in range(3):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(tool_name="web_fetch", call_id=call_id, args={"url": "https://example.com/blocked"}))
        messages.append(_tool_error(tool_name="web_fetch", call_id=call_id, content="Web fetch failed: timed out"))
    request = ToolCallRequest(
        tool_call={"name": "web_fetch", "args": {"url": "https://example.com/blocked"}, "id": "call-next"},
        tool=None,
        state={"messages": messages},
        runtime=None,
    )

    result = middleware.wrap_tool_call(request, lambda next_request: ToolMessage(content="should not run", tool_call_id="call-next"))

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "Do not fetch the same URL again" in result.content
    assert "web_search" in result.content


def test_http_error_tool_result_is_marked_as_error() -> None:
    middleware = ToolBudgetMiddleware()
    request = ToolCallRequest(
        tool_call={"name": "web_fetch", "args": {"url": "https://example.com/blocked"}, "id": "call-1"},
        tool=None,
        state={"messages": [HumanMessage(content="fetch news")]},
        runtime=None,
    )

    result = middleware.wrap_tool_call(
        request,
        lambda next_request: ToolMessage(
            content="HTTP error 401 fetching https://example.com/blocked",
            name="web_fetch",
            tool_call_id="call-1",
        ),
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"


def test_host_shell_json_nonzero_exit_is_marked_as_error() -> None:
    middleware = ToolBudgetMiddleware()
    request = ToolCallRequest(
        tool_call={"name": "host_shell", "args": {"command": "missing-command"}, "id": "call-1"},
        tool=None,
        state={"messages": [HumanMessage(content="run command")]},
        runtime=None,
    )

    result = middleware.wrap_tool_call(
        request,
        lambda next_request: ToolMessage(
            content='{"command":"missing-command","exit_code":127,"stderr":"not found"}',
            name="host_shell",
            tool_call_id="call-1",
        ),
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"


def test_six_total_tool_errors_require_capability_discovery() -> None:
    middleware = ToolBudgetMiddleware(discover_tool_errors=6)
    messages = [HumanMessage(content="complete task")]
    for index, tool_name in enumerate(["bash", "ls", "read_file", "bash", "ls", "read_file"]):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(tool_name=tool_name, call_id=call_id))
        messages.append(_tool_error(tool_name=tool_name, call_id=call_id, content="Error: failed"))
    request = ToolCallRequest(
        tool_call={"name": "write_file", "args": {"path": "/tmp/out", "content": "x"}, "id": "call-next"},
        tool=None,
        state={"messages": messages},
        runtime=None,
    )

    result = middleware.wrap_tool_call(request, lambda next_request: ToolMessage(content="should not run", tool_call_id="call-next"))

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "capability discovery" in result.content
    assert "web_search" not in result.content


def test_final_failure_after_model_records_soft_review_without_replacing_tool_calls() -> None:
    middleware = ToolBudgetMiddleware(final_failure_errors=9)
    messages = [HumanMessage(content="complete task")]
    for index in range(9):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(call_id=call_id))
        messages.append(_tool_error(call_id=call_id, content="Error: repeated failure"))
    final_call = _ai_tool_call(call_id="call-final")
    messages.append(final_call)

    update = middleware.after_model({"messages": messages}, None)

    assert update is not None
    assert "messages" not in update
    assert update["runtime"]["tool_recovery"]["stage"] == "final_soft_review"
    assert final_call.tool_calls


def test_recovery_guard_errors_count_toward_soft_review() -> None:
    middleware = ToolBudgetMiddleware(final_failure_errors=9)
    messages = [HumanMessage(content="complete task")]
    for index in range(6):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(call_id=call_id))
        messages.append(_tool_error(call_id=call_id, content="Error: repeated failure"))
    for index in range(3):
        guard_id = f"guard-{index}"
        messages.append(_ai_tool_call(call_id=guard_id))
        messages.append(
            ToolMessage(
                content="Error: this turn has 6 tool failures. Recovery policy requires capability discovery / tool/settings review now.",
                name="bash",
                tool_call_id=guard_id,
                status="error",
            )
        )
    messages.append(_ai_tool_call(call_id="call-final"))

    update = middleware.after_model({"messages": messages}, None)

    assert update is not None
    assert "messages" not in update
    assert update["runtime"]["tool_recovery"]["error_count"] == 9
    assert update["runtime"]["tool_recovery"]["stage"] == "final_soft_review"


def test_recovery_guidance_does_not_reset_guard_loop_to_repair() -> None:
    middleware = ToolBudgetMiddleware(final_failure_errors=9)
    messages = [HumanMessage(content="complete task")]
    for index in range(6):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(call_id=call_id))
        messages.append(_tool_error(call_id=call_id, content="Error: repeated failure"))
    for index in range(3):
        guard_id = f"guard-{index}"
        messages.append(_ai_tool_call(call_id=guard_id))
        messages.append(
            ToolMessage(
                content="Error: this turn has 6 tool failures. Recovery policy requires capability discovery / tool/settings review now.",
                name="bash",
                tool_call_id=guard_id,
                status="error",
            )
        )

    update = middleware.before_model({"messages": messages}, None)

    assert update is not None
    assert update["runtime"]["tool_recovery"]["stage"] == "final_soft_constraint"
    guidance = update["messages"][0].content
    assert "runtime_self_constraint_reflection" in guidance
    assert "tool_failure_loop" in guidance
    assert "search_memory" in guidance
    assert "archival_memory_insert" in guidance


def test_final_recovery_guidance_after_reflection_remains_advisory() -> None:
    middleware = ToolBudgetMiddleware(final_failure_errors=9)
    messages = [HumanMessage(content="complete task")]
    for index in range(9):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(call_id=call_id))
        messages.append(_tool_error(call_id=call_id, content="Error: repeated failure"))
    messages.append(
        SystemMessage(
            content=(
                "<runtime_self_constraint_reflection>\n"
                "kind: tool_failure_loop\n"
                "This is advisory guidance for model self-regulation, not a hard stop.\n"
                "</runtime_self_constraint_reflection>"
            )
        )
    )
    messages.append(_ai_tool_call(call_id="call-after-reflection"))
    messages.append(_tool_error(call_id="call-after-reflection", content="Error: repeated failure"))

    update = middleware.before_model({"messages": messages}, None)

    assert update is not None
    guidance = update["messages"][0].content
    assert "final recovery review point" in guidance
    assert "not a hard stop" in guidance
    assert "stopped the task" not in guidance
    assert update["runtime"]["tool_recovery"]["stage"] == "final"


def test_source_constrained_soft_budget_injects_advisory_without_stopping() -> None:
    middleware = ToolBudgetMiddleware(max_tool_messages=2)
    messages = [
        HumanMessage(content="只从官方网站搜索美国基金回报率前三"),
        _ai_tool_call(tool_name="web_search", call_id="call-1"),
        ToolMessage(
            content="Search results unavailable: fallback results did not satisfy the explicit source constraint.",
            name="web_search",
            tool_call_id="call-1",
        ),
        _ai_tool_call(tool_name="web_search", call_id="call-2"),
        ToolMessage(
            content="Search backend unavailable: this query includes an explicit source constraint.",
            name="web_search",
            tool_call_id="call-2",
        ),
    ]

    update = middleware.before_model({"messages": messages}, None)

    assert update is not None
    guidance = update["messages"][0].content
    assert "tool_soft_budget_policy" in guidance
    assert "这是软上限，不是硬停止" in guidance
    assert update["runtime"]["tool_soft_budget"]["soft_budget"] == 2

    messages.append(_ai_tool_call(tool_name="web_fetch", call_id="call-final"))
    assert middleware.after_model({"messages": messages}, None) is None


def test_unconstrained_soft_budget_advises_without_summarizing_available_results() -> None:
    middleware = ToolBudgetMiddleware(max_tool_messages=2)
    messages = [
        HumanMessage(content="搜索一些公开资料"),
        _ai_tool_call(tool_name="web_search", call_id="call-1"),
        ToolMessage(
            content="1. Example public result\nhttps://example.com\nUseful public context.",
            name="web_search",
            tool_call_id="call-1",
        ),
        _ai_tool_call(tool_name="web_fetch", call_id="call-2"),
        ToolMessage(
            content="Fetched page summary with relevant details.",
            name="web_fetch",
            tool_call_id="call-2",
        ),
    ]

    update = middleware.before_model({"messages": messages}, None)

    assert update is not None
    guidance = update["messages"][0].content
    assert "tool_soft_budget_policy" in guidance
    assert "可以继续调用必要工具" in guidance

    messages.append(_ai_tool_call(tool_name="web_search", call_id="call-final"))
    assert middleware.after_model({"messages": messages}, None) is None


def test_runtime_context_soft_budget_controls_advisory_without_default_hard_cap() -> None:
    middleware = ToolBudgetMiddleware()
    messages = [
        HumanMessage(content="inspect deeply"),
        _ai_tool_call(call_id="call-1"),
        ToolMessage(content="result 1", name="bash", tool_call_id="call-1"),
        _ai_tool_call(call_id="call-2"),
        ToolMessage(content="result 2", name="bash", tool_call_id="call-2"),
    ]

    update = middleware.before_model(
        {"messages": messages},
        _Runtime({"tool_budget_policy": {"soft_tool_messages": 2}}),
    )

    assert update is not None
    assert "tool_soft_budget_policy" in update["messages"][0].content
    assert update["runtime"]["tool_soft_budget"]["soft_budget"] == 2


def test_tool_budget_counts_only_latest_user_turn_tool_messages() -> None:
    middleware = ToolBudgetMiddleware(max_tool_messages=2)
    messages = [
        HumanMessage(content="previous task"),
        _ai_tool_call(call_id="old-1"),
        ToolMessage(content="old result 1", name="bash", tool_call_id="old-1"),
        _ai_tool_call(call_id="old-2"),
        ToolMessage(content="old result 2", name="bash", tool_call_id="old-2"),
        HumanMessage(content="new task"),
        _ai_tool_call(call_id="new-1"),
        ToolMessage(content="new result 1", name="bash", tool_call_id="new-1"),
        _ai_tool_call(call_id="new-final"),
    ]

    assert middleware.after_model({"messages": messages}, None) is None


def test_soft_budget_does_not_summarize_directory_listing_noise() -> None:
    middleware = ToolBudgetMiddleware(max_tool_messages=2)
    noisy_listing = """总计 10632
-rw-rw-r-- 1 sieve-pub sieve-pub 1353095 5月 11 23:19 langgraph.log
-rw-rw-r-- 1 sieve-pub sieve-pub 9342357 5月 11 23:19 nginx-access.log
/var/log/letsencrypt/letsencrypt.log /home/sieve-pub/public-workspace/octoagent/backend
"""
    messages = [
        HumanMessage(content="请分析基金回报率"),
        _ai_tool_call(tool_name="bash", call_id="call-1"),
        ToolMessage(content=noisy_listing, name="bash", tool_call_id="call-1"),
        _ai_tool_call(tool_name="ls", call_id="call-2"),
        ToolMessage(content=noisy_listing, name="ls", tool_call_id="call-2"),
    ]

    update = middleware.before_model({"messages": messages}, None)

    assert update is not None
    guidance = update["messages"][0].content
    assert "tool_soft_budget_policy" in guidance
    assert "nginx-access.log" not in guidance

    messages.append(_ai_tool_call(tool_name="web_search", call_id="call-final"))
    assert middleware.after_model({"messages": messages}, None) is None


# octo_tool_loop_hard_stop
def test_duplicate_tool_call_hard_limit_aborts_turn_with_command_end() -> None:
    """Once the same (tool, args) is repeated past the hard limit despite soft
    recovery guards, the middleware aborts the turn via Command(goto=END)
    instead of returning yet another advisory ToolMessage that the model would
    again ignore.
    """
    from src.agents.middlewares.tool_budget_middleware import (
        _DUPLICATE_TOOL_CALL_HARD_LIMIT,
        _TOOL_LOOP_HARD_STOP_KEY,
    )

    middleware = ToolBudgetMiddleware()
    args = {"command": "curl -s http://10.0.0.1/../etc/passwd"}
    messages = [HumanMessage(content="scan ports")]
    # Build HARD_LIMIT prior identical successful calls so the next call's
    # dup_count equals _DUPLICATE_TOOL_CALL_HARD_LIMIT.
    for index in range(_DUPLICATE_TOOL_CALL_HARD_LIMIT):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(call_id=call_id, args=args))
        messages.append(
            ToolMessage(content="200", name="bash", tool_call_id=call_id, status="success")
        )
    request = ToolCallRequest(
        tool_call={"name": "bash", "args": args, "id": "call-next"},
        tool=None,
        state={"messages": messages},
        runtime=None,
    )

    def handler(_req: ToolCallRequest) -> ToolMessage:  # pragma: no cover - must not run
        raise AssertionError("handler must not execute once hard-stop is reached")

    result = middleware.wrap_tool_call(request, handler)

    assert isinstance(result, Command)
    assert result.goto == END
    update_messages = result.update["messages"]
    assert len(update_messages) == 2
    tool_msg, ai_msg = update_messages
    assert isinstance(tool_msg, ToolMessage)
    assert tool_msg.status == "error"
    assert tool_msg.additional_kwargs.get(_TOOL_LOOP_HARD_STOP_KEY) is True
    assert isinstance(ai_msg, AIMessage)
    assert "循环" in ai_msg.content


def test_duplicate_tool_call_hard_limit_also_triggers_when_prior_errors_present() -> None:
    """Hard-stop must fire regardless of whether prior calls failed or
    succeeded. The previous design gated duplicate detection behind a
    `not entries:` check, allowing infinite loops once any tool error existed.
    """
    from src.agents.middlewares.tool_budget_middleware import (
        _DUPLICATE_TOOL_CALL_HARD_LIMIT,
        _TOOL_LOOP_HARD_STOP_KEY,
    )

    middleware = ToolBudgetMiddleware()
    args = {"command": "curl http://target/x"}
    messages = [HumanMessage(content="probe target")]
    # Mix some unrelated tool errors first to populate `entries`.
    for index in range(2):
        call_id = f"err-{index}"
        messages.append(_ai_tool_call(tool_name="bash", call_id=call_id, args={"command": "broken"}))
        messages.append(_tool_error(tool_name="bash", call_id=call_id, content="Error: failed"))
    # Then HARD_LIMIT identical duplicates.
    for index in range(_DUPLICATE_TOOL_CALL_HARD_LIMIT):
        call_id = f"dup-{index}"
        messages.append(_ai_tool_call(call_id=call_id, args=args))
        messages.append(
            ToolMessage(content="ok", name="bash", tool_call_id=call_id, status="success")
        )
    request = ToolCallRequest(
        tool_call={"name": "bash", "args": args, "id": "call-final"},
        tool=None,
        state={"messages": messages},
        runtime=None,
    )

    result = middleware.wrap_tool_call(
        request,
        lambda _r: ToolMessage(content="ok", name="bash", tool_call_id="call-final"),
    )

    assert isinstance(result, Command)
    assert result.goto == END
    assert result.update["messages"][0].additional_kwargs.get(_TOOL_LOOP_HARD_STOP_KEY) is True


def test_duplicate_write_todos_does_not_hit_hard_stop() -> None:
    """write_todos has its own planning-noop guard and is exempt from the
    hard-stop branch to avoid prematurely ending plan-revision loops."""
    from src.agents.middlewares.tool_budget_middleware import _DUPLICATE_TOOL_CALL_HARD_LIMIT

    middleware = ToolBudgetMiddleware()
    args = {"todos": [{"content": "x", "status": "in_progress"}]}
    messages = [HumanMessage(content="plan")]
    for index in range(_DUPLICATE_TOOL_CALL_HARD_LIMIT):
        call_id = f"call-{index}"
        messages.append(_ai_tool_call(tool_name="write_todos", call_id=call_id, args=args))
        messages.append(ToolMessage(content="ok", name="write_todos", tool_call_id=call_id))
    request = ToolCallRequest(
        tool_call={"name": "write_todos", "args": args, "id": "call-next"},
        tool=None,
        state={"messages": messages},
        runtime=None,
    )

    result = middleware.wrap_tool_call(
        request,
        lambda _r: ToolMessage(content="ok", name="write_todos", tool_call_id="call-next"),
    )

    # write_todos hits the planning-noop guard (a ToolMessage), never the
    # Command(goto=END) hard-stop branch.
    assert not isinstance(result, Command)
