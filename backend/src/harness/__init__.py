"""Octoagent harness layer.

Owns the *runtime hygiene* of agent runs:

* Orphaned-run detection + cancellation (:mod:`src.harness.lifecycle`)
* Declarative hooks (:mod:`src.harness.hooks`)
* Wall-clock + max-turns budget (:mod:`src.harness.budget`)
* AgentMiddleware ↔ hooks bridge (:mod:`src.harness.hook_middleware`)
* Postgres-backed run journal (:mod:`src.harness.run_journal`)

Inspired by HKUDS/OpenHarness ``engine/`` + ``hooks/`` but adapted to the
LangGraph + langchain.agents runtime.
"""

from src.harness.budget import BudgetMiddleware, maybe_build_budget_middleware
from src.harness.deep_agent import (  # noqa: F401
    AgentRole,
    ContextFileStore,
    DeepAgentConfig,
    DeepAgentExecutor,
    MemoryEntry,
    MemoryStore,
    Skill,
    SkillRegistry,
    StepPriority,
    StepStatus,
    TaskPlan,
    TaskStep,
    get_skill_registry,
)
from src.harness.hook_middleware import (
    HookDispatchMiddleware,
    install_default_hooks,
)
from src.harness.hooks import (
    AggregatedHookResult,
    HookContext,
    HookEvent,
    HookExecutor,
    HookRegistry,
    HookResult,
    get_hook_executor,
    get_hook_registry,
    hook,
)
from src.harness.lifecycle import (
    OrphanRunSweeper,
    start_orphan_run_sweeper_task,
    stop_orphan_run_sweeper_task,
    sweep_orphaned_runs_once,
)
from src.harness.run_journal import (
    find_stale_runs,
    heartbeat,
    init_run_journal,
    mark_orphans_on_startup,
    record_run_finished,
    record_run_started,
    shutdown_run_journal,
)

__all__ = [
    "AgentRole",
    "ContextFileStore",
    "DeepAgentConfig",
    "DeepAgentExecutor",
    "MemoryEntry",
    "MemoryStore",
    "Skill",
    "SkillRegistry",
    "StepPriority",
    "StepStatus",
    "TaskPlan",
    "TaskStep",
    "get_skill_registry",
    # lifecycle / sweeper
    "OrphanRunSweeper",
    "sweep_orphaned_runs_once",
    "start_orphan_run_sweeper_task",
    "stop_orphan_run_sweeper_task",
    # hooks
    "HookEvent",
    "HookResult",
    "AggregatedHookResult",
    "HookContext",
    "HookRegistry",
    "HookExecutor",
    "get_hook_registry",
    "get_hook_executor",
    "hook",
    # middleware bridge
    "HookDispatchMiddleware",
    "install_default_hooks",
    # budget
    "BudgetMiddleware",
    "maybe_build_budget_middleware",
    # journal
    "init_run_journal",
    "shutdown_run_journal",
    "record_run_started",
    "record_run_finished",
    "heartbeat",
    "find_stale_runs",
    "mark_orphans_on_startup",
]
