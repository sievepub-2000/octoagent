from __future__ import annotations

import logging
from collections.abc import Callable

from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.runnables import RunnableConfig

from src.config.app_config import get_app_config
from src.config.paths import Paths
from src.config.summarization_config import get_summarization_config
from src.models import create_chat_model

from .runtime import runtime_config_value

logger = logging.getLogger(__name__)


class LeadAgentMiddlewareBuilder:
    def __init__(
        self,
        *,
        app_config_getter=get_app_config,
        summarization_config_getter=get_summarization_config,
        chat_model_factory=create_chat_model,
        thread_data_middleware_cls,
        uploads_middleware_cls,
        continuation_middleware_cls,
        sandbox_middleware_cls,
        dangling_tool_call_middleware_cls,
        title_middleware_cls,
        memory_middleware_cls,
        runtime_state_middleware_cls,
        view_image_middleware_cls,
        subagent_limit_middleware_cls,
        session_compaction_middleware_cls,
        skill_evolution_middleware_cls,
        clarification_middleware_cls,
    ):
        self._app_config_getter = app_config_getter
        self._summarization_config_getter = summarization_config_getter
        self._chat_model_factory = chat_model_factory
        self._thread_data_middleware_cls = thread_data_middleware_cls
        self._uploads_middleware_cls = uploads_middleware_cls
        self._continuation_middleware_cls = continuation_middleware_cls
        self._sandbox_middleware_cls = sandbox_middleware_cls
        self._dangling_tool_call_middleware_cls = dangling_tool_call_middleware_cls
        self._title_middleware_cls = title_middleware_cls
        self._memory_middleware_cls = memory_middleware_cls
        self._runtime_state_middleware_cls = runtime_state_middleware_cls
        self._view_image_middleware_cls = view_image_middleware_cls
        self._subagent_limit_middleware_cls = subagent_limit_middleware_cls
        self._session_compaction_middleware_cls = session_compaction_middleware_cls
        self._skill_evolution_middleware_cls = skill_evolution_middleware_cls
        self._clarification_middleware_cls = clarification_middleware_cls

    def create_summarization_middleware(self) -> SummarizationMiddleware | None:
        config = self._summarization_config_getter()
        if not config.enabled:
            return None

        trigger = None
        if config.trigger is not None:
            if isinstance(config.trigger, list):
                trigger = [t.to_tuple() for t in config.trigger]
            else:
                trigger = config.trigger.to_tuple()

        model = (
            config.model_name
            if config.model_name
            else self._chat_model_factory(thinking_enabled=False)
        )
        kwargs: dict[str, object] = {
            "model": model,
            "trigger": trigger,
            "keep": config.keep.to_tuple(),
        }
        if config.trim_tokens_to_summarize is not None:
            kwargs["trim_tokens_to_summarize"] = config.trim_tokens_to_summarize
        if config.summary_prompt is not None:
            kwargs["summary_prompt"] = config.summary_prompt
        return SummarizationMiddleware(**kwargs)

    @staticmethod
    def create_todo_list_middleware(
        is_plan_mode: bool,
        *,
        todo_middleware_factory: Callable[..., object],
    ):
        if not is_plan_mode:
            return None

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
        return todo_middleware_factory(
            system_prompt=system_prompt,
            tool_description=tool_description,
        )

    def build(
        self,
        config: RunnableConfig,
        *,
        model_name: str | None,
        agent_name: str | None = None,
        create_todo_list_middleware_fn: Callable[[bool], object | None],
        create_summarization_middleware_fn: Callable[[], object | None],
    ) -> list[object]:
        middlewares: list[object] = [
            self._thread_data_middleware_cls(),
            self._uploads_middleware_cls(),
            self._continuation_middleware_cls(),
            self._sandbox_middleware_cls(),
            self._dangling_tool_call_middleware_cls(),
        ]

        summarization_middleware = create_summarization_middleware_fn()
        if summarization_middleware is not None:
            middlewares.append(summarization_middleware)

        is_plan_mode = runtime_config_value(config, "is_plan_mode", False)
        todo_list_middleware = create_todo_list_middleware_fn(is_plan_mode)
        if todo_list_middleware is not None:
            middlewares.append(todo_list_middleware)

        middlewares.append(self._title_middleware_cls())
        middlewares.append(self._memory_middleware_cls(agent_name=agent_name))

        app_config = self._app_config_getter()
        model_config = app_config.get_model_config(model_name) if model_name else None
        fallback_models = model_config.fallback_models if model_config is not None else []
        middlewares.append(
            self._runtime_state_middleware_cls(
                model_name=model_name,
                fallback_models=fallback_models,
            )
        )
        if model_config is not None and model_config.supports_vision:
            middlewares.append(self._view_image_middleware_cls())

        if runtime_config_value(config, "subagent_enabled", False):
            max_concurrent_subagents = runtime_config_value(
                config,
                "max_concurrent_subagents",
                3,
            )
            middlewares.append(
                self._subagent_limit_middleware_cls(
                    max_concurrent=max_concurrent_subagents
                )
            )

        middlewares.append(self._session_compaction_middleware_cls())
        try:
            paths = Paths()
            middlewares.append(
                self._skill_evolution_middleware_cls(
                    data_dir=paths.base_dir / "skill_evolution",
                    skills_root=paths.base_dir / "skills",
                )
            )
        except Exception:
            logger.warning("SkillEvolutionMiddleware not loaded", exc_info=True)

        middlewares.append(self._clarification_middleware_cls())
        return middlewares
