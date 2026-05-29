"""Task tool for delegating work to subagents."""

import asyncio
import logging
import uuid
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langgraph.config import get_stream_writer
from langgraph.typing import ContextT

from src.agents.lead_agent.prompt import (
    get_capability_guide_prompt_section,
    get_skills_prompt_section,
)
from src.agents.subagents import SubagentExecutor, get_subagent_config
from src.agents.subagents.catalog import get_subagent_names
from src.agents.subagents.executor import (
    SubagentStatus,
    cleanup_background_task,
    get_background_task_events,
    get_background_task_result,
)
from src.agents.subagents.policy import resolve_subagent_config
from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)


def _status_value(status: object) -> str:
    return getattr(status, "value", str(status))


def _enum_status_value(enum_cls: object, name: str, fallback: str) -> str:
    member = getattr(enum_cls, name, fallback)
    return _status_value(member)


@tool("task", parse_docstring=True)
async def task_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    description: str,
    prompt: str,
    subagent_type: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    max_turns: int | None = None,
) -> str:
    """Delegate a task to a specialized subagent that runs in its own context.

    Subagents help you:
    - Preserve context by keeping exploration and implementation separate
    - Handle complex multi-step tasks autonomously
    - Execute commands or operations in isolated contexts

    Common subagent types:
    - **general-purpose**: A capable agent for complex, multi-step tasks that require
      both exploration and action. Use when the task requires complex reasoning,
      multiple dependent steps, or would benefit from isolated context.
    - **bash**: Command execution specialist for running bash commands. Use for
      git operations, build processes, or when command output would be verbose.

    Additional dynamically loaded subagent types may be available from the subagent
    catalog (for example agency-* roles). If an unknown type is requested, the tool
    returns the current catalog names.

    When to use this tool:
    - Complex tasks requiring multiple steps or tools
    - Tasks that produce verbose output
    - When you want to isolate context from the main conversation
    - Parallel research or exploration tasks

    When NOT to use this tool:
    - Simple, single-step operations (use tools directly)
    - Tasks requiring user interaction or clarification

    Args:
        description: A short (3-5 word) description of the task for logging/display. ALWAYS PROVIDE THIS PARAMETER FIRST.
        prompt: The task description for the subagent. Be specific and clear about what needs to be done. ALWAYS PROVIDE THIS PARAMETER SECOND.
        subagent_type: The type of subagent to use. ALWAYS PROVIDE THIS PARAMETER THIRD.
        max_turns: Optional maximum number of agent turns. Defaults to subagent's configured max.
    """
    subagent_type = subagent_type.strip()
    config = get_subagent_config(subagent_type)
    if config is None:
        available = ", ".join(get_subagent_names())
        return f"Error: Unknown subagent type '{subagent_type}'. Available: {available}"

    skills_section = get_skills_prompt_section()
    capability_section = get_capability_guide_prompt_section()
    prompt_sections = [section for section in (skills_section, capability_section) if section]
    if prompt_sections:
        config.system_prompt = config.system_prompt + "\n\n" + "\n\n".join(prompt_sections)
    config, _budget = resolve_subagent_config(
        config,
        max_turns=max_turns,
    )

    # Extract parent context from runtime
    sandbox_state = None
    thread_data = None
    thread_id = None
    parent_model = None
    trace_id = None

    if runtime is not None:
        sandbox_state = runtime.state.get("sandbox")
        thread_data = runtime.state.get("thread_data")
        thread_id = (runtime.context or {}).get("thread_id")

        # Try to get parent model from configurable
        metadata = runtime.config.get("metadata", {})
        parent_model = metadata.get("model_name")

        # Get or generate trace_id for distributed tracing
        trace_id = metadata.get("trace_id") or str(uuid.uuid4())[:8]

    # Get available tools (excluding task tool to prevent nesting)
    # Lazy import to avoid circular dependency
    from src.tools import get_available_tools

    # Subagents should not have subagent tools enabled (prevent recursive nesting)
    tools = get_available_tools(model_name=parent_model, subagent_enabled=False)

    # Create executor
    executor = SubagentExecutor(
        config=config,
        tools=tools,
        parent_model=parent_model,
        sandbox_state=sandbox_state,
        thread_data=thread_data,
        thread_id=thread_id,
        trace_id=trace_id,
    )

    # Start background execution (always async to prevent blocking)
    # Use tool_call_id as task_id for better traceability
    task_id = executor.execute_async(prompt, task_id=tool_call_id)

    # Poll for task completion in backend (removes need for LLM to poll)
    last_message_count = 0  # Track how many AI messages we've already sent

    logger.info(f"[trace={trace_id}] Started background task {task_id} (subagent={subagent_type}, timeout={config.timeout_seconds}s)")

    writer = get_stream_writer()
    # Send Task Started message'
    writer({"type": "task_started", "task_id": task_id, "description": description})

    max_wait_seconds = config.timeout_seconds + 60
    deadline_seconds = max_wait_seconds
    while deadline_seconds >= 0:
        result = get_background_task_result(task_id)

        if result is None:
            logger.error(f"[trace={trace_id}] Task {task_id} not found in background tasks")
            writer({"type": "task_failed", "task_id": task_id, "error": "Task disappeared from background tasks"})
            cleanup_background_task(task_id)
            return f"Error: Task {task_id} disappeared from background tasks"

        logger.debug(f"[trace={trace_id}] Task {task_id} status: {result.status.value}")

        # Check for new AI messages and send task_running events
        current_message_count = len(result.ai_messages)
        if current_message_count > last_message_count:
            # Send task_running event for each new message
            for i in range(last_message_count, current_message_count):
                message = result.ai_messages[i]
                writer(
                    {
                        "type": "task_running",
                        "task_id": task_id,
                        "message": message,
                        "message_index": i + 1,  # 1-based index for display
                        "total_messages": current_message_count,
                    }
                )
                logger.info(f"[trace={trace_id}] Task {task_id} sent message #{i + 1}/{current_message_count}")
            last_message_count = current_message_count

        for event in get_background_task_events(task_id):
            logger.debug(
                "[trace=%s] Task %s event=%s status=%s",
                trace_id,
                task_id,
                event["type"],
                event["status"],
            )

        status_value = _status_value(result.status)
        if status_value == _status_value(SubagentStatus.COMPLETED):
            writer({"type": "task_completed", "task_id": task_id, "result": result.result})
            cleanup_background_task(task_id)
            return f"Task Succeeded. Result: {result.result}"
        elif status_value in {
            _enum_status_value(SubagentStatus, "FAILED", "failed"),
            _enum_status_value(SubagentStatus, "ADMISSION_REJECTED", "admission_rejected"),
            _enum_status_value(SubagentStatus, "CANCELLED", "cancelled"),
            _enum_status_value(SubagentStatus, "INTERRUPTED", "interrupted"),
        }:
            writer({"type": "task_failed", "task_id": task_id, "error": result.error})
            logger.error(f"[trace={trace_id}] Task {task_id} failed: {result.error}")
            cleanup_background_task(task_id)
            return f"Task failed. Error: {result.error}"
        elif status_value == _enum_status_value(SubagentStatus, "TIMED_OUT", "timed_out"):
            writer({"type": "task_timed_out", "task_id": task_id, "error": result.error})
            logger.warning(f"[trace={trace_id}] Task {task_id} timed out: {result.error}")
            cleanup_background_task(task_id)
            return f"Task timed out. Error: {result.error}"

        await asyncio.sleep(1)
        deadline_seconds -= 1

    timeout_minutes = config.timeout_seconds // 60
    logger.error(f"[trace={trace_id}] Task {task_id} polling timed out after {max_wait_seconds}s")
    writer({"type": "task_timed_out", "task_id": task_id})
    return f"Task polling timed out after {timeout_minutes} minutes. This may indicate the background task is stuck. Status: {_status_value(result.status)}"
