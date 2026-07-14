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
    assert '<continuation_handoff version="2">' in str(patched[0].content)
    assert "<historical_context>" in str(patched[0].content)
    assert "Compacted task memory" in str(patched[0].content)
    assert "Authoritative active contract" in str(patched[0].content)
    assert "Completed steps — do not repeat" in str(patched[0].content)
    assert "Pending steps" in str(patched[0].content)
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


def test_completed_continuation_returns_stop_answer() -> None:
    answer = ContinuationMiddleware._completed_continuation_answer(
        {
            "continue_trigger": "continue",
            "continue_task_state": {
                "goal": "Fix the web UI",
                "status": "completed",
                "completed_steps": ["Reproduced the issue", "Patched the layout", "Ran regression tests"],
                "pending_steps": [],
                "evidence": ["pytest passed"],
            },
            "continue_todos": [{"content": "Document result", "status": "completed"}],
        }
    )

    assert answer is not None
    assert "already completed" in answer
    assert "Fix the web UI" in answer
    assert "Ran regression tests" in answer


def test_completed_continuation_does_not_stop_when_pending_work_exists() -> None:
    answer = ContinuationMiddleware._completed_continuation_answer(
        {
            "continue_trigger": "continue",
            "continue_task_state": {
                "goal": "Fix the web UI",
                "status": "completed",
                "completed_steps": ["Reproduced the issue"],
                "pending_steps": ["Run browser verification"],
            },
        }
    )

    assert answer is None


def test_v2_contract_is_authoritative_and_does_not_force_execution() -> None:
    message = ContinuationMiddleware()._build_message(
        {
            "continue_trigger": "continue",
            "continue_from_thread_id": "source-thread",
            "continue_contract": {
                "version": 2,
                "objective": "Repair context continuation without goal drift",
                "constraints": ["Wait for confirmation before deployment"],
                "acceptance_criteria": ["Preserve the next action across rollover"],
                "completed_steps": ["Diagnose the failure"],
                "pending_steps": ["Implement the approved repair"],
                "next_action": "Implement the approved repair",
            },
            "continue_memory_summary": "Historical background only.",
        }
    )

    assert message is not None
    content = str(message.content)
    assert '<continuation_handoff version="2">' in content
    assert "Authoritative active contract" in content
    assert "Wait for confirmation before deployment" in content
    assert "Historical background only" in content
    assert "call a tool" not in content
    assert "The latest explicit user instruction takes precedence" in content
