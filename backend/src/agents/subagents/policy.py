"""Budget and admission policy for delegated subagent jobs."""

from __future__ import annotations

import logging
import os
from dataclasses import replace

from src.agents.subagents.config import SubagentConfig
from src.runtime.config.subagents_config import get_subagents_app_config

from .contracts import ACTIVE_SUBAGENT_STATUSES, SubagentBudget, SubagentResult

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _long_task_defaults() -> tuple[int, int]:
    """Return long-task defaults without importing the agent package.

    Importing ``src.agents.resource_profile`` here creates a circular import
    through runtime-state middleware. This policy layer uses the same
    environment knobs, with the large-host defaults used on 2号机.
    """

    return (
        _env_int("OCTO_WORKSPACE_RECURSION", 500_000),
        _env_int("OCTO_WORKSPACE_TIMEOUT_S", 3_600),
    )


def estimate_available_memory_gb() -> float | None:
    """Best-effort available host memory estimate in GiB."""
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemAvailable:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            return float(parts[1]) / 1024 / 1024
    except Exception:
        logger.exception("Failed to read host memory for subagent policy")
    return None


def is_host_memory_oom_critical(available_gb: float | None = None) -> bool:
    """Return True only when host memory is below the hard OOM threshold."""
    app_config = get_subagents_app_config()
    if not app_config.enable_system_memory_guard:
        return False
    resolved_available_gb = estimate_available_memory_gb() if available_gb is None else available_gb
    if resolved_available_gb is None:
        return False
    return resolved_available_gb < app_config.oom_critical_available_memory_gb


def resolve_subagent_config(
    base_config: SubagentConfig,
    *,
    max_turns: int | None = None,
    model_name: str | None = None,
) -> tuple[SubagentConfig, SubagentBudget]:
    """Resolve final runtime config and budget for a delegated job."""
    use_host_long_task_default = base_config.max_turns is None
    default_turns, default_timeout = _long_task_defaults()
    effective_turns = base_config.max_turns or default_turns
    resolved_timeout = max(base_config.timeout_seconds, default_timeout) if use_host_long_task_default else base_config.timeout_seconds
    if max_turns is not None:
        effective_turns = max(1, int(max_turns))
        resolved_timeout = max(base_config.timeout_seconds, effective_turns * 10)
        if effective_turns >= 100:
            resolved_timeout = max(resolved_timeout, 1800)

    resolved_model = model_name if base_config.model == "inherit" else base_config.model
    resolved_config = replace(
        base_config,
        max_turns=effective_turns,
        timeout_seconds=resolved_timeout,
        model=base_config.model,
    )
    return resolved_config, SubagentBudget(
        max_turns=effective_turns,
        timeout_seconds=resolved_timeout,
        model=resolved_model,
    )


def check_admission(jobs: list[SubagentResult], *, thread_id: str | None) -> str | None:
    """Return a rejection reason if a job should not be admitted."""
    app_config = get_subagents_app_config()
    if len(jobs) >= app_config.max_total_subagent_jobs:
        return f"Global delegated-task ceiling reached ({len(jobs)}/{app_config.max_total_subagent_jobs}). Wait for terminal subagent history to be pruned before spawning another."

    active_jobs = [item for item in jobs if item.status in ACTIVE_SUBAGENT_STATUSES]

    if len(active_jobs) >= app_config.max_concurrent_subagents:
        return f"Subagent concurrency limit reached ({len(active_jobs)}/{app_config.max_concurrent_subagents}). Wait for a running delegated task to finish before spawning another."

    if thread_id is not None:
        thread_jobs = [item for item in active_jobs if item.thread_id == thread_id]
        if len(thread_jobs) >= app_config.max_active_subagents_per_thread:
            return f"Thread subagent limit reached ({len(thread_jobs)}/{app_config.max_active_subagents_per_thread}). This thread already has too many delegated workers running."
        thread_total = [item for item in jobs if item.thread_id == thread_id]
        if len(thread_total) >= app_config.max_total_subagents_per_thread:
            return f"Thread delegated-task ceiling reached ({len(thread_total)}/{app_config.max_total_subagents_per_thread}). Reduce branch breadth or wait for tasks to be cleaned up."

    if app_config.enable_system_memory_guard:
        available_gb = estimate_available_memory_gb()
        if is_host_memory_oom_critical(available_gb):
            return f"Host memory guard blocked subagent scheduling (available={available_gb:.1f} GiB, oom_critical<{app_config.oom_critical_available_memory_gb:.1f} GiB). This prevents local-model OOM and host thrashing."
    return None
