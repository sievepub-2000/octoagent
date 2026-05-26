from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.middlewares.continuation_middleware import ContinuationMiddleware


def test_continuation_context_is_injected_without_mutating_user_message() -> None:
    """Continuation metadata should stay hidden from the visible user turn."""
    middleware = ContinuationMiddleware()
    user_message = HumanMessage(content="please continue the implementation")
    patched = middleware._inject(
        [user_message],
        {
            "continue_trigger": "continue",
            "continue_from_thread_id": "source-thread",
            "continue_from_title": "Previous work",
            "continue_message_count": 12,
            "continue_recent_messages": [
                {"role": "human", "content": "fix continuation UX"},
                {"role": "ai", "content": "identified visible bootstrap issue"},
            ],
            "continue_memory_summary": "Compacted task memory: continue from verifier.",
            "continue_todos": [
                {"content": "verify context handoff", "status": "in_progress"},
                {"content": "write final report", "status": "pending"},
            ],
            "continue_task_state": {
                "goal": "finish continuation repair",
                "status": "active",
                "completed_steps": ["fix skipped tests"],
                "pending_steps": ["validate resume"],
                "next_action": "validate resume",
            },
            "continue_workflows": [
                {
                    "title": "Continuation refactor",
                    "mode": "task",
                    "status": "in_progress",
                }
            ],
        },
    )

    assert patched is not None
    assert isinstance(patched[0], SystemMessage)
    assert patched[0].name == "workflow_continue"
    assert patched[1] is user_message
    assert patched[1].content == "please continue the implementation"
    assert "<continue_context>" in str(patched[0].content)
    assert "Extracted continuation memory" in str(patched[0].content)
    assert "Compacted task memory" in str(patched[0].content)
    assert "Active task todo state to continue" in str(patched[0].content)
    assert "Completed steps (do not repeat)" in str(patched[0].content)
    assert "Pending steps to resume" in str(patched[0].content)
    assert "verify context handoff" in str(patched[0].content)


def test_continuation_context_is_not_injected_twice() -> None:
    """Repeated model calls should not stack duplicate continuation context."""
    middleware = ContinuationMiddleware()
    messages = [
        SystemMessage(content="existing hidden context", name="workflow_continue"),
        HumanMessage(content="continue"),
    ]

    patched = middleware._inject(messages, {"continue_trigger": "continue"})

    assert patched is None


def test_continuation_context_is_capped_before_injection() -> None:
    middleware = ContinuationMiddleware()
    user_message = HumanMessage(content="continue")
    patched = middleware._inject(
        [user_message],
        {
            "continue_trigger": "continue",
            "continue_from_thread_id": "source-thread",
            "continue_recent_messages": [
                {"role": "tool", "content": "x" * 30_000},
                {"role": "ai", "content": "y" * 30_000},
            ],
            "continue_todos": [
                {"content": "z" * 20_000, "status": "in_progress"},
            ],
        },
    )

    assert patched is not None
    continuation = patched[0]
    assert isinstance(continuation, SystemMessage)
    assert len(str(continuation.content)) <= 8_200
    assert "continuation context shortened" in str(continuation.content)
