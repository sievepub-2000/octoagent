import logging

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.runnables import RunnableConfig

from src.agents.lead_agent.builder import LeadAgentBuilder
from src.agents.lead_agent.kernel import HermesLeadAgentKernel
from src.agents.lead_agent.prompt import apply_prompt_template
from src.agents.lead_agent.runtime import (
    LeadAgentRuntimeResolver,
    embedded_backup_system_prompt,
    runtime_config_value,
)
from src.agents.middlewares.clarification_middleware import ClarificationMiddleware
from src.agents.middlewares.client_command_middleware import ClientCommandMiddleware
from src.agents.middlewares.continuation_middleware import ContinuationMiddleware
from src.agents.middlewares.dangerous_tool_confirmation_middleware import DangerousToolConfirmationMiddleware
from src.agents.middlewares.dangling_tool_call_middleware import DanglingToolCallMiddleware
from src.agents.middlewares.execution_review_middleware import ExecutionReviewMiddleware
from src.agents.middlewares.execution_mode_middleware import ExecutionModeMiddleware
from src.agents.middlewares.goal_contract_middleware import GoalContractProducerMiddleware
from src.agents.middlewares.goal_drift_middleware import GoalDriftMiddleware
from src.agents.middlewares.instruction_contract_middleware import InstructionContractMiddleware
from src.agents.middlewares.lesson_injection_middleware import LessonInjectionMiddleware
from src.agents.middlewares.memory_middleware import MemoryMiddleware
from src.agents.middlewares.runtime_state_middleware import RuntimeStateMiddleware
from src.agents.middlewares.session_compaction_middleware import SessionCompactionMiddleware
from src.agents.middlewares.skill_evolution_middleware import SkillEvolutionMiddleware
from src.agents.middlewares.subagent_limit_middleware import SubagentLimitMiddleware
from src.agents.middlewares.task_state_middleware import TaskStateMiddleware
from src.agents.middlewares.thread_data_middleware import ThreadDataMiddleware
from src.agents.middlewares.title_middleware import TitleMiddleware
from src.agents.middlewares.todo_middleware import TodoMiddleware
from src.agents.middlewares.tool_budget_middleware import ToolBudgetMiddleware
from src.agents.middlewares.uploads_middleware import UploadsMiddleware
from src.agents.middlewares.view_image_middleware import ViewImageMiddleware
from src.agents.thread_state import ThreadState
from src.harness import (
    HookDispatchMiddleware,
    install_default_hooks,
    maybe_build_budget_middleware,
)
from src.models import create_chat_model
from src.runtime.config.app_config import get_app_config
from src.runtime.config.paths import resolve_configured_default_model_name
from src.runtime.config.summarization_config import get_summarization_config
from src.tools.sandbox.middleware import SandboxMiddleware

logger = logging.getLogger(__name__)


def _resolve_compaction_context_tokens(model_config, app_config) -> int:
    max_context_tokens = getattr(model_config, "max_context_tokens", None) if model_config is not None else None
    if isinstance(max_context_tokens, int) and max_context_tokens > 0:
        return max_context_tokens
    configured_windows = [int(value) for value in (getattr(model, "max_context_tokens", None) for model in getattr(app_config, "models", [])) if isinstance(value, int) and value > 0]
    if configured_windows:
        return max(configured_windows)
    return 32_000


def _resolve_model_name(requested_model_name: str | None = None) -> str:
    """Resolve a runtime model name safely, falling back to default if invalid. Returns None if no models are configured."""
    app_config = get_app_config()
    default_model_name = resolve_configured_default_model_name(model.name for model in app_config.models)
    if default_model_name is None:
        logger.warning("No configured chat model found; embedded bootstrap model will be used as emergency default.")
        return "__embedded_bootstrap__"

    if requested_model_name and app_config.get_model_config(requested_model_name):
        return requested_model_name

    if requested_model_name and requested_model_name != default_model_name:
        logger.warning(f"Model '{requested_model_name}' not found in config; fallback to default model '{default_model_name}'.")
    return default_model_name


def _create_summarization_middleware() -> SummarizationMiddleware | None:
    """Create and configure the summarization middleware from config."""
    config = get_summarization_config()

    if not config.enabled:
        return None

    # Prepare trigger parameter
    trigger = None
    if config.trigger is not None:
        if isinstance(config.trigger, list):
            trigger = [t.to_tuple() for t in config.trigger]
        else:
            trigger = config.trigger.to_tuple()

    # Prepare keep parameter
    keep = config.keep.to_tuple()

    # Prepare model parameter
    if config.model_name:
        model = config.model_name
    else:
        # Use a lightweight model for summarization to save costs
        # Falls back to default model if not explicitly specified
        model = create_chat_model(thinking_enabled=False)

    # Prepare kwargs
    kwargs = {
        "model": model,
        "trigger": trigger,
        "keep": keep,
    }

    if config.trim_tokens_to_summarize is not None:
        kwargs["trim_tokens_to_summarize"] = config.trim_tokens_to_summarize

    if config.summary_prompt is not None:
        kwargs["summary_prompt"] = config.summary_prompt

    return SummarizationMiddleware(**kwargs)


def _create_todo_list_middleware(is_plan_mode: bool) -> TodoMiddleware | None:
    """Create and configure the TodoList middleware.

    Args:
        is_plan_mode: Whether to enable plan mode with TodoList middleware.

    Returns:
        TodoMiddleware instance if plan mode is enabled, None otherwise.
    """
    if not is_plan_mode:
        return None

    # Custom prompts matching OctoAgent's style
    system_prompt = """
<todo_list_system>
You have access to the `write_todos` tool to help you manage and track complex multi-step objectives.

**CRITICAL RULES:**
- Mark todos as completed IMMEDIATELY after finishing each step - do NOT batch completions
- Keep EXACTLY ONE task as `in_progress` at any time (unless tasks can run in parallel)
- Update the todo list in REAL-TIME as you work - this gives users visibility into your progress
- DO NOT use this tool for simple tasks (< 3 steps) - just complete them directly

**When to Use:**
This tool is designed for complex objectives that require systematic tracking:
- Complex multi-step tasks requiring 3+ distinct steps
- Non-trivial tasks needing careful planning and execution
- User explicitly requests a todo list
- User provides multiple tasks (numbered or comma-separated list)
- The plan may need revisions based on intermediate results

**When NOT to Use:**
- Single, straightforward tasks
- Trivial tasks (< 3 steps)
- Purely conversational or informational requests
- Simple tool calls where the approach is obvious

**Best Practices:**
- Break down complex tasks into smaller, actionable steps
- Use clear, descriptive task names
- Remove tasks that become irrelevant
- Add new tasks discovered during implementation
- Don't be afraid to revise the todo list as you learn more

**Task Management:**
Writing todos takes time and tokens - use it when helpful for managing complex problems, not for simple requests.
</todo_list_system>
"""

    tool_description = """Use this tool to create and manage a structured task list for complex work sessions.

**IMPORTANT: Only use this tool for complex tasks (3+ steps). For simple requests, just do the work directly.**

## When to Use

Use this tool in these scenarios:
1. **Complex multi-step tasks**: When a task requires 3 or more distinct steps or actions
2. **Non-trivial tasks**: Tasks requiring careful planning or multiple operations
3. **User explicitly requests todo list**: When the user directly asks you to track tasks
4. **Multiple tasks**: When users provide a list of things to be done
5. **Dynamic planning**: When the plan may need updates based on intermediate results

## When NOT to Use

Skip this tool when:
1. The task is straightforward and takes less than 3 steps
2. The task is trivial and tracking provides no benefit
3. The task is purely conversational or informational
4. It's clear what needs to be done and you can just do it

## How to Use

1. **Starting a task**: Mark it as `in_progress` BEFORE beginning work
2. **Completing a task**: Mark it as `completed` IMMEDIATELY after finishing
3. **Updating the list**: Add new tasks, remove irrelevant ones, or update descriptions as needed
4. **Multiple updates**: You can make several updates at once (e.g., complete one task and start the next)

## Task States

- `pending`: Task not yet started
- `in_progress`: Currently working on (can have multiple if tasks run in parallel)
- `completed`: Task finished successfully

## Task Completion Requirements

**CRITICAL: Only mark a task as completed when you have FULLY accomplished it.**

Never mark a task as completed if:
- There are unresolved issues or errors
- Work is partial or incomplete
- You encountered blockers preventing completion
- You couldn't find necessary resources or dependencies
- Quality standards haven't been met

If blocked, keep the task as `in_progress` and create a new task describing what needs to be resolved.

## Best Practices

- Create specific, actionable items
- Break complex tasks into smaller, manageable steps
- Use clear, descriptive task names
- Update task status in real-time as you work
- Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
- Remove tasks that are no longer relevant
- **IMPORTANT**: When you write the todo list, mark your first task(s) as `in_progress` immediately
- **IMPORTANT**: Unless all tasks are completed, always have at least one task `in_progress` to show progress

Being proactive with task management demonstrates thoroughness and ensures all requirements are completed successfully.

**Remember**: If you only need a few tool calls to complete a task and it's clear what to do, it's better to just do the task directly and NOT use this tool at all.
"""

    return TodoMiddleware(system_prompt=system_prompt, tool_description=tool_description)


# ThreadDataMiddleware must be before SandboxMiddleware to ensure thread_id is available
# UploadsMiddleware should be after ThreadDataMiddleware to access thread_id
# DanglingToolCallMiddleware patches missing ToolMessages before model sees the history
# SummarizationMiddleware should be early to reduce context before other processing
# TodoListMiddleware should be before ClarificationMiddleware to allow todo management
# TitleMiddleware generates title after first exchange
# MemoryMiddleware queues conversation for memory update (after TitleMiddleware)
# ViewImageMiddleware should be before ClarificationMiddleware to inject image details before LLM
# ClarificationMiddleware should be last to intercept clarification requests after model calls
def _build_middlewares(config: RunnableConfig, model_name: str | None, agent_name: str | None = None):
    """Build middleware chain based on runtime configuration.

    Args:
        config: Runtime configuration containing configurable options like is_plan_mode.
        agent_name: If provided, MemoryMiddleware will use per-agent memory storage.

    Returns:
        List of middleware instances.
    """
    middlewares = [
        ThreadDataMiddleware(),
        UploadsMiddleware(),
        ContinuationMiddleware(),
        ClientCommandMiddleware(),
        ExecutionModeMiddleware(),
        SandboxMiddleware(),
        DanglingToolCallMiddleware(),
    ]

    # Add summarization middleware if enabled
    summarization_middleware = _create_summarization_middleware()
    if summarization_middleware is not None:
        middlewares.append(summarization_middleware)

    # Add TodoList middleware if plan mode is enabled
    is_plan_mode = runtime_config_value(config, "is_plan_mode", False)
    todo_list_middleware = _create_todo_list_middleware(is_plan_mode)
    if todo_list_middleware is not None:
        middlewares.append(todo_list_middleware)

    # Add TitleMiddleware
    middlewares.append(GoalContractProducerMiddleware())  # sprint-2: emit GoalContract once per thread
    middlewares.append(TitleMiddleware())

    # Add MemoryMiddleware (after TitleMiddleware)
    middlewares.append(MemoryMiddleware(agent_name=agent_name))

    # Add ViewImageMiddleware only if the current model supports vision.
    # Use the resolved runtime model_name from make_lead_agent to avoid stale config values.
    app_config = get_app_config()
    model_config = app_config.get_model_config(model_name) if model_name else None
    fallback_models = model_config.fallback_models if model_config is not None else []
    middlewares.append(RuntimeStateMiddleware(model_name=model_name, fallback_models=fallback_models))
    middlewares.append(InstructionContractMiddleware())
    middlewares.append(TaskStateMiddleware())
    if model_config is not None and model_config.supports_vision:
        middlewares.append(ViewImageMiddleware())

    # Phase-2 harness: ProgressStall / StepReflection are now registered as
    # AFTER_MODEL hooks via install_default_hooks(); we only keep the single
    # HookDispatchMiddleware in the agent build, plus the budget guard.
    install_default_hooks()
    _budget_mw = maybe_build_budget_middleware()
    if _budget_mw is not None:
        middlewares.append(_budget_mw)
    middlewares.append(HookDispatchMiddleware())
    middlewares.append(DangerousToolConfirmationMiddleware())
    middlewares.append(ToolBudgetMiddleware())

    # Add SubagentLimitMiddleware to truncate excess parallel task calls
    subagent_enabled = runtime_config_value(config, "subagent_enabled", False)
    # Goal drift detection and lesson injection should be active for ALL tasks,
    # not just subagent mode — they improve task accuracy universally.
    middlewares.append(LessonInjectionMiddleware())  # sprint-1 P0: inject top-K lessons into system prompt
    middlewares.append(GoalDriftMiddleware(every_n=5, drift_threshold=0.45, window=5))  # sprint-2: detect goal drift

    if subagent_enabled:
        max_concurrent_subagents = runtime_config_value(
            config,
            "max_concurrent_subagents",
            3,
        )
        middlewares.append(SubagentLimitMiddleware(max_concurrent=max_concurrent_subagents))
        # CriticMiddleware migrated to harness hook (see install_default_hooks);
        # we keep the conditional branch so the hook is *only* effective when
        # subagents are enabled — matches pre-migration semantics.
        from src.harness import get_hook_registry as _ghk

        # If critic hook absent (e.g. subagent path is the only place it runs),
        # ensure the bridge is set up.
        if _ghk().event_count(__import__("src.harness", fromlist=["HookEvent"]).HookEvent.ON_CRITIC_CHECK) == 0:
            install_default_hooks()

    # SessionCompactionMiddleware — compress long context before LLM call (claw-code)
    middlewares.append(
        SessionCompactionMiddleware(
            max_context_tokens=_resolve_compaction_context_tokens(model_config, app_config),
        )
    )
    middlewares.append(ExecutionReviewMiddleware())

    # SkillEvolutionMiddleware — record execution traces and trigger evolution
    try:
        from src.runtime.config.paths import Paths

        paths = Paths()
        data_dir = paths.base_dir / "skill_evolution"
        skills_root = paths.base_dir / "skills"
        middlewares.append(SkillEvolutionMiddleware(data_dir=data_dir, skills_root=skills_root))
    except Exception:
        logger.warning("SkillEvolutionMiddleware not loaded", exc_info=True)

    # ClarificationMiddleware should always be last
    middlewares.append(ClarificationMiddleware())
    return middlewares


def make_lead_agent(config: RunnableConfig):
    # Lazy import to avoid circular dependency
    from src.tools import get_available_tools
    from src.tools.builtins import setup_agent

    kernel = HermesLeadAgentKernel(
        runtime_resolver=LeadAgentRuntimeResolver(
            app_config_getter=get_app_config,
        ),
        builder=LeadAgentBuilder(
            create_agent_fn=create_agent,
            create_chat_model_fn=create_chat_model,
            get_available_tools_fn=get_available_tools,
            build_middlewares_fn=_build_middlewares,
            apply_prompt_template_fn=apply_prompt_template,
            state_schema=ThreadState,
            setup_agent_tool=setup_agent,
            embedded_backup_prompt_fn=embedded_backup_system_prompt,
        ),
    )
    return kernel.build(config)
