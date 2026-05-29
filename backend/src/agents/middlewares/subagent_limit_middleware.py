"""Middleware to enforce maximum concurrent subagent tool calls per model response."""

import logging
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from src.agents.subagents.policy import is_host_memory_oom_critical
from src.runtime.config.subagents_config import get_subagents_app_config

logger = logging.getLogger(__name__)

# Valid range for max_concurrent_subagents
MIN_SUBAGENT_LIMIT = 2
MAX_SUBAGENT_LIMIT = 4


def _clamp_subagent_limit(value: int) -> int:
    """Clamp subagent limit to valid range [2, 4]."""
    return max(MIN_SUBAGENT_LIMIT, min(MAX_SUBAGENT_LIMIT, value))


class SubagentLimitMiddleware(AgentMiddleware[AgentState]):
    """Trim excess 'task' tool calls only when the host is OOM-critical.

    When an LLM generates more than max_concurrent parallel task tool calls
    in one response, the subagent admission layer normally accepts or rejects
    each delegated task. This middleware only rewrites tool calls when the host
    is below the hard OOM threshold and starting extra delegated workers would
    risk host thrashing.

    Args:
        max_concurrent: Maximum number of concurrent subagent calls allowed.
            Defaults to MAX_CONCURRENT_SUBAGENTS (3). Clamped to [2, 4].
    """

    def __init__(self, max_concurrent: int | None = None):
        super().__init__()
        if max_concurrent is None:
            max_concurrent = get_subagents_app_config().max_concurrent_subagents
        self.max_concurrent = _clamp_subagent_limit(max_concurrent)

    def _truncate_task_calls(self, state: AgentState) -> dict | None:
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        if getattr(last_msg, "type", None) != "ai":
            return None

        tool_calls = getattr(last_msg, "tool_calls", None)
        if not tool_calls:
            return None

        if not is_host_memory_oom_critical():
            return None

        # Count task tool calls
        task_indices = [i for i, tc in enumerate(tool_calls) if tc.get("name") == "task"]
        if len(task_indices) <= self.max_concurrent:
            return None

        # Build set of indices to drop (excess task calls beyond the limit)
        indices_to_drop = set(task_indices[self.max_concurrent :])
        truncated_tool_calls = [tc for i, tc in enumerate(tool_calls) if i not in indices_to_drop]

        # Sprint-1 P0 fix (anti goal-drift): the historical behaviour silently
        # dropped excess `task` calls only under OOM-critical host memory. The
        # model received no signal at all. We still truncate (the admission
        # layer cannot run those workers safely under OOM), but we now:
        #   1. Log structured WARNING so operators can monitor truncation rate.
        #   2. Add a one-line meta entry in the AIMessage's response_metadata
        #      so observability layers can surface "N queued" to the trace UI.
        #   3. Rely on the updated lead_agent prompt (Sprint-1 C.7) which
        #      explicitly tells the LLM that excess calls are deferred — so it
        #      will re-issue them naturally in the next turn.
        # We intentionally do NOT emit synthetic ToolMessage stubs: those would
        # create orphan tool_call_ids (the removed tool_calls are not present in
        # the truncated AIMessage) which would violate the LLM API tool-call/
        # tool-result pairing invariant on the next turn.
        dropped_count = len(indices_to_drop)
        logger.warning(
            "Deferred %d excess `task` tool call(s) to next turn (cap=%d, oom_critical=True)",
            dropped_count,
            self.max_concurrent,
        )

        meta = dict(getattr(last_msg, "response_metadata", {}) or {})
        meta.setdefault("octoagent_subagent_truncation", {}).update(
            {
                "deferred_count": dropped_count,
                "cap": self.max_concurrent,
                "reason": "host_memory_oom_critical",
            }
        )
        updated_msg = last_msg.model_copy(update={"tool_calls": truncated_tool_calls, "response_metadata": meta})
        return {"messages": [updated_msg]}

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._truncate_task_calls(state)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._truncate_task_calls(state)
