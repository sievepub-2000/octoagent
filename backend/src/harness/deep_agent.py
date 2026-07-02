"""Deep Agent execution engine for OctoAgent harness.

Architecture inspired by:
- langchain-ai/deepagents: planning-first, filesystem context offload,
  sub-agent delegation, memory-first protocol, skills system
- affaan-m/everything-claude-code: orchestration team pattern,
  continuous learning, context rot prevention, research-first workflows

Provides autonomous multi-step task execution with:
- Recursive goal decomposition (Planning Tool / write_todos)
- Tool chain orchestration with retry and parallel execution
- Filesystem-based context offload (prevents context rot)
- Memory-first protocol (check memories before acting)
- Sub-agent delegation with isolated context windows
- Goal tracking, drift detection, and checkpoint reviews
- Skill loading (reusable behaviors on demand)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# Core Types
# ============================================================


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class StepPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class AgentRole(str, Enum):
    """ECC-inspired team roles for orchestration."""

    ORCHESTRATOR = "orchestrator"
    PLANNER = "planner"
    RESEARCHER = "researcher"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    SECURITY = "security"


# ============================================================
# Task Planning (deepagents write_todos pattern)
# ============================================================


@dataclass
class TaskStep:
    """A single step in a deep agent execution plan."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    priority: StepPriority = StepPriority.NORMAL
    assigned_role: AgentRole = AgentRole.EXECUTOR
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    depends_on: list[str] = field(default_factory=list)
    # Context offload: large results are saved to filesystem
    result_file: str | None = None
    # Retry tracking
    retry_count: int = 0
    max_retries: int = 2


@dataclass
class TaskPlan:
    """Execution plan following deepagents planning-first pattern."""

    goal: str
    steps: list[TaskStep] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # Memory-first: facts learned during execution
    learned_facts: list[str] = field(default_factory=list)
    # Context rot prevention: checkpoint hashes
    checkpoint_hashes: list[str] = field(default_factory=list)

    @property
    def pending_steps(self) -> list[TaskStep]:
        return [s for s in self.steps if s.status == StepStatus.PENDING]

    @property
    def completed_steps(self) -> list[TaskStep]:
        return [s for s in self.steps if s.status == StepStatus.COMPLETED]

    @property
    def failed_steps(self) -> list[TaskStep]:
        return [s for s in self.steps if s.status == StepStatus.FAILED]

    @property
    def blocked_steps(self) -> list[TaskStep]:
        return [s for s in self.steps if s.status == StepStatus.BLOCKED]

    @property
    def progress_ratio(self) -> float:
        if not self.steps:
            return 0.0
        done = len([s for s in self.steps if s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)])
        return done / len(self.steps)

    def add_step(
        self,
        description: str,
        *,
        tool_name: str | None = None,
        tool_args: dict[str, Any] | None = None,
        priority: StepPriority = StepPriority.NORMAL,
        role: AgentRole = AgentRole.EXECUTOR,
        depends_on: list[str] | None = None,
    ) -> TaskStep:
        """Add a step to the plan (deepagents write_todos pattern)."""
        step = TaskStep(
            description=description,
            tool_name=tool_name,
            tool_args=tool_args or {},
            priority=priority,
            assigned_role=role,
            depends_on=depends_on or [],
        )
        self.steps.append(step)
        return step

    def to_checkpoint(self) -> dict[str, Any]:
        """Serialize to a compact checkpoint for task state persistence."""
        return {
            "goal": self.goal,
            "status": self.status.value,
            "progress": f"{self.progress_ratio:.0%}",
            "total_steps": len(self.steps),
            "completed": len(self.completed_steps),
            "failed": len(self.failed_steps),
            "pending": len(self.pending_steps),
            "blocked": len(self.blocked_steps),
            "learned_facts": self.learned_facts[-5:],
            "steps": [
                {
                    "id": s.id,
                    "desc": s.description[:200],
                    "status": s.status.value,
                    "tool": s.tool_name,
                    "priority": s.priority.value,
                    "role": s.assigned_role.value,
                }
                for s in self.steps
            ],
        }

    def to_continuation_summary(self) -> str:
        """Generate a human-readable summary for context continuation."""
        lines = [f"Goal: {self.goal}", f"Progress: {self.progress_ratio:.0%}"]
        if self.completed_steps:
            lines.append("Completed:")
            for s in self.completed_steps[-5:]:
                lines.append(f"  ✓ {s.description[:100]}")
        if self.pending_steps:
            lines.append("Pending:")
            for s in self.pending_steps[:5]:
                lines.append(f"  ○ {s.description[:100]}")
        if self.failed_steps:
            lines.append("Failed:")
            for s in self.failed_steps[-3:]:
                lines.append(f"  ✗ {s.description[:80]}: {s.error or 'unknown'}")
        if self.learned_facts:
            lines.append("Learned facts:")
            for fact in self.learned_facts[-3:]:
                lines.append(f"  • {fact[:120]}")
        return "\n".join(lines)


# ============================================================
# Filesystem Context Offload (deepagents pattern)
# ============================================================


class ContextFileStore:
    """Offload large tool outputs to filesystem to prevent context rot.

    Inspired by deepagents filesystem-based context management:
    - Large outputs are written to files instead of kept in messages
    - Agent reads back only what it needs via read_file
    - Prevents context window bloat in long-running tasks
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else Path("/tmp/octoagent_context")
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def store(self, content: str, label: str = "output") -> str:
        """Store content to filesystem, return the file path."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{label}_{timestamp}_{content_hash}.txt"
        filepath = self._base_dir / filename
        filepath.write_text(content, encoding="utf-8")
        logger.debug("ContextFileStore: wrote %d chars to %s", len(content), filepath)
        return str(filepath)

    def retrieve(self, filepath: str, max_chars: int = 8000) -> str:
        """Read content back from filesystem with optional truncation."""
        path = Path(filepath)
        if not path.exists():
            return f"[File not found: {filepath}]"
        content = path.read_text(encoding="utf-8")
        if len(content) > max_chars:
            return content[:max_chars] + f"\n[... truncated, {len(content) - max_chars} chars remaining]"
        return content

    def cleanup(self, max_age_hours: int = 24) -> int:
        """Remove files older than max_age_hours. Returns count removed."""
        cutoff = time.time() - max_age_hours * 3600
        removed = 0
        for f in self._base_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        return removed


# ============================================================
# Memory-First Protocol (deepagents pattern)
# ============================================================


@dataclass
class MemoryEntry:
    """A fact or preference learned during execution."""

    content: str
    source: str = "execution"
    confidence: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    tags: list[str] = field(default_factory=list)


class MemoryStore:
    """In-session memory for the deep agent.

    Implements the deepagents memory-first protocol:
    1. Before acting, check if relevant knowledge exists
    2. After learning something new, store it
    3. Memories persist across context compaction cycles
    """

    def __init__(self) -> None:
        self._entries: list[MemoryEntry] = []

    def add(self, content: str, *, source: str = "execution", tags: list[str] | None = None) -> None:
        self._entries.append(
            MemoryEntry(
                content=content,
                source=source,
                tags=tags or [],
            )
        )

    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """Simple keyword-based search. In production, use embedding similarity."""
        query_lower = query.lower()
        scored = []
        for entry in self._entries:
            content_lower = entry.content.lower()
            score = sum(1 for word in query_lower.split() if word in content_lower)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: -x[0])
        return [entry for _, entry in scored[:limit]]

    def to_context(self, limit: int = 10) -> str:
        """Serialize recent memories for injection into context."""
        if not self._entries:
            return ""
        recent = self._entries[-limit:]
        lines = ["[Agent Memories]"]
        for entry in recent:
            tags = f" [{', '.join(entry.tags)}]" if entry.tags else ""
            lines.append(f"- {entry.content}{tags}")
        return "\n".join(lines)

    @property
    def count(self) -> int:
        return len(self._entries)


# ============================================================
# Executor Types
# ============================================================


ToolExecutor = Callable[[str, dict[str, Any]], Any]
AsyncToolExecutor = Callable[[str, dict[str, Any]], Any]


# ============================================================
# Configuration
# ============================================================


@dataclass
class DeepAgentConfig:
    """Configuration for deep agent execution.

    Combines deepagents and ECC best practices:
    - Planning-first with configurable step limits
    - Context offload thresholds
    - Parallel execution controls
    - Goal drift detection
    - Memory-first protocol toggle
    """

    # Execution limits. step_timeout_seconds is retained for config
    # compatibility, but asynchronous steps are not hard-cancelled by the
    # harness. The OOM/resource guard is the only hard stop.
    max_steps: int = 50
    max_retries_per_step: int = 2
    step_timeout_seconds: float = 120.0

    # Parallel execution (deepagents sub-agent pattern)
    enable_parallel: bool = True
    max_parallel: int = 4

    # Context management (deepagents filesystem pattern)
    context_offload_threshold: int = 4000  # chars before offloading to file
    enable_context_offload: bool = True

    # Goal tracking (ECC context rot prevention)
    goal_drift_threshold: float = 0.3
    checkpoint_interval: int = 5

    # Memory-first protocol (deepagents)
    enable_memory_first: bool = True
    max_memories: int = 50

    # Research-first workflow (ECC pattern)
    research_before_execute: bool = True

    # Context store path
    context_store_path: str | None = None

    # Realtime inspection + safe skill capture
    enable_work_bus: bool = True
    enable_skill_solidification: bool = True
    solidification_min_steps: int = 4
    solidification_output_dir: str | None = None


# ============================================================
# Work Bus + Skill Solidification helpers
# ============================================================


_WORK_BUS_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="deep-agent-work-bus",
)


def _compact_payload(value: Any, *, max_chars: int = 2000) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return value if len(value) <= max_chars else value[:max_chars] + "... [truncated]"
    try:
        encoded = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        encoded = str(value)
    if len(encoded) > max_chars:
        encoded = encoded[:max_chars] + "... [truncated]"
    try:
        return json.loads(encoded)
    except json.JSONDecodeError:
        return encoded


def _plan_id(plan: TaskPlan) -> str:
    value = plan.metadata.get("plan_id")
    if not value:
        value = uuid.uuid4().hex
        plan.metadata["plan_id"] = value
    return str(value)


def _thread_id(plan: TaskPlan) -> str:
    for key in ("thread_id", "run_id", "session_id"):
        value = plan.metadata.get(key)
        if value:
            return str(value)
    value = _plan_id(plan)
    plan.metadata["thread_id"] = value
    return value


def _step_kind(step: TaskStep) -> str:
    return {
        StepStatus.COMPLETED: "step_completed",
        StepStatus.FAILED: "step_failed",
        StepStatus.BLOCKED: "step_blocked",
        StepStatus.SKIPPED: "step_skipped",
        StepStatus.RUNNING: "step_started",
    }.get(step.status, "step_updated")


def _step_event_payload(plan: TaskPlan, kind: str, step: TaskStep | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "thread_id": _thread_id(plan),
        "plan_id": _plan_id(plan),
        "kind": kind,
        "status": plan.status.value,
        "title": plan.goal[:180],
        "payload": {
            "goal": plan.goal,
            "progress_ratio": plan.progress_ratio,
            "total_steps": len(plan.steps),
            "completed_steps": len(plan.completed_steps),
            "failed_steps": len(plan.failed_steps),
            "blocked_steps": len(plan.blocked_steps),
        },
    }
    if step is not None:
        base.update(
            {
                "step_id": step.id,
                "status": step.status.value,
                "title": step.description[:180],
                "detail": step.error,
                "role": step.assigned_role.value,
                "tool_name": step.tool_name,
                "input": _compact_payload(step.tool_args),
                "output": _compact_payload(step.result),
                "error": step.error,
                "duration_ms": step.duration_ms,
                "payload": {
                    **base["payload"],
                    "retry_count": step.retry_count,
                    "max_retries": step.max_retries,
                    "result_file": step.result_file,
                    "depends_on": step.depends_on,
                    "priority": step.priority.value,
                },
            }
        )
    return base


async def _publish_work_bus_event(plan: TaskPlan, kind: str, step: TaskStep | None = None) -> None:
    try:
        from src.harness.work_bus_redis import get_work_bus

        await get_work_bus().publish_step_event(**_step_event_payload(plan, kind, step))
    except Exception:
        logger.debug("DeepAgent: Work Bus event skipped", exc_info=True)


def _publish_work_bus_event_nowait(plan: TaskPlan, kind: str, step: TaskStep | None = None) -> None:
    coro = _publish_work_bus_event(plan, kind, step)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _WORK_BUS_EXECUTOR.submit(asyncio.run, coro)
    else:
        loop.create_task(coro, name=f"deep-agent-work-bus-{kind}")


def _skill_slug(goal: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", goal.lower()).strip("-")
    return slug[:48] or "deep-agent-workflow"


def _clean_skill_text(value: Any, *, max_chars: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = text.replace("---", "-").replace("`", "'")
    return text[:max_chars]


class SelfSolidificationExecutor:
    """Capture successful multi-step plans as reusable custom skills."""

    def __init__(self, config: DeepAgentConfig) -> None:
        self._config = config

    def maybe_solidify(self, plan: TaskPlan) -> str | None:
        if not self._config.enable_skill_solidification:
            return None
        if plan.status != StepStatus.COMPLETED:
            return None
        if len(plan.completed_steps) < self._config.solidification_min_steps:
            return None
        if plan.metadata.get("solidified_skill_path"):
            return str(plan.metadata["solidified_skill_path"])

        root = self._resolve_output_root()
        if root is None:
            return None
        plan_hash = hashlib.sha256(plan.to_continuation_summary().encode()).hexdigest()[:10]
        name = f"deep-agent-{_skill_slug(plan.goal)}-{plan_hash}"
        skill_dir = root / name
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            plan.metadata["solidified_skill_path"] = str(skill_file)
            return str(skill_file)

        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(self._render_skill(plan, name), encoding="utf-8")
        plan.metadata["solidified_skill_path"] = str(skill_file)
        try:
            from src.storage.skills.loader import invalidate_skills_cache

            invalidate_skills_cache()
        except Exception:
            logger.debug("DeepAgent: could not invalidate skills cache", exc_info=True)
        logger.info("DeepAgent: solidified plan as skill %s", skill_file)
        return str(skill_file)

    def _resolve_output_root(self) -> Path | None:
        if self._config.solidification_output_dir:
            return Path(self._config.solidification_output_dir)
        try:
            from src.storage.skills.loader import get_skills_root_path

            return get_skills_root_path() / "custom" / "auto-captured"
        except Exception:
            logger.debug("DeepAgent: skills root unavailable", exc_info=True)
            return None

    def _render_skill(self, plan: TaskPlan, name: str) -> str:
        description = _clean_skill_text(f"Auto-captured workflow for: {plan.goal}", max_chars=140)
        lines = [
            "---",
            f"name: {name}",
            f"description: {description}",
            "license: proprietary",
            "---",
            "",
            f"# {name}",
            "",
            "Captured from a successful DeepAgent workflow.",
            "",
            "## Goal",
            "",
            _clean_skill_text(plan.goal, max_chars=1000),
            "",
            "## Execution Pattern",
            "",
        ]
        for index, step in enumerate(plan.completed_steps, start=1):
            tool = f" using `{step.tool_name}`" if step.tool_name else ""
            lines.append(f"{index}. {_clean_skill_text(step.description)}{tool}.")
        if plan.learned_facts:
            lines.extend(["", "## Learned Facts", ""])
            for fact in plan.learned_facts[-8:]:
                lines.append(f"- {_clean_skill_text(fact)}")
        lines.append("")
        return "\n".join(lines)


# ============================================================
# Deep Agent Executor
# ============================================================


class DeepAgentExecutor:
    """Autonomous multi-step task executor.

    Architecture layers (following deepagents stack model):
    1. LangGraph runtime — state persistence, streaming, checkpoints
    2. LangChain framework — tools, models, chains
    3. Deep Agent harness — planning, context, delegation, skills

    Execution flow:
    1. Memory-first: check existing knowledge
    2. Plan: decompose goal into steps (write_todos)
    3. Research: gather information before executing (ECC pattern)
    4. Execute: run steps with retry, parallel, and context offload
    5. Review: checkpoint and detect goal drift
    6. Learn: store new facts in memory
    """

    def __init__(
        self,
        config: DeepAgentConfig | None = None,
        tool_executor: ToolExecutor | None = None,
        async_tool_executor: AsyncToolExecutor | None = None,
    ) -> None:
        self._config = config or DeepAgentConfig()
        self._tool_executor = tool_executor
        self._async_tool_executor = async_tool_executor
        self._execution_log: list[dict[str, Any]] = []
        self._memory = MemoryStore()
        self._context_store = ContextFileStore(base_dir=self._config.context_store_path) if self._config.enable_context_offload else None
        self._solidification = SelfSolidificationExecutor(self._config)

    @property
    def memory(self) -> MemoryStore:
        return self._memory

    @property
    def config(self) -> DeepAgentConfig:
        return self._config

    def _should_offload(self, result: Any) -> bool:
        """Check if a tool result should be offloaded to filesystem."""
        if not self._config.enable_context_offload or self._context_store is None:
            return False
        text = str(result) if result is not None else ""
        return len(text) > self._config.context_offload_threshold

    def _offload_result(self, step: TaskStep, result: Any) -> str:
        """Offload large result to filesystem, return summary."""
        text = str(result)
        label = step.tool_name or "step"
        filepath = self._context_store.store(text, label=label)
        step.result_file = filepath
        # Return a compact summary instead of full content
        preview = text[:500] if len(text) > 500 else text
        return f"[Output saved to {filepath}] Preview: {preview}"

    def _check_memory_first(self, step: TaskStep) -> str | None:
        """Memory-first protocol: check if we already know the answer."""
        if not self._config.enable_memory_first:
            return None
        relevant = self._memory.search(step.description, limit=3)
        if relevant:
            return "\n".join(f"- {e.content}" for e in relevant)
        return None

    def execute_step(self, step: TaskStep) -> TaskStep:
        """Execute a single step synchronously."""
        if step.tool_name is None or self._tool_executor is None:
            step.status = StepStatus.SKIPPED
            step.error = "No tool specified or no executor available"
            return step

        # Memory-first check
        memory_hit = self._check_memory_first(step)
        if memory_hit:
            logger.info("DeepAgent: memory hit for step %s", step.id)
            step.result = f"[From memory] {memory_hit}"
            # Don't skip — still execute to verify, but log the memory context

        step.status = StepStatus.RUNNING
        t0 = time.perf_counter()

        while step.retry_count <= step.max_retries:
            try:
                result = self._tool_executor(step.tool_name, step.tool_args)
                # Context offload for large results
                if self._should_offload(result):
                    result = self._offload_result(step, result)
                step.result = result
                step.status = StepStatus.COMPLETED
                step.completed_at = datetime.now(UTC).isoformat()
                break
            except Exception as exc:
                step.retry_count += 1
                if step.retry_count > step.max_retries:
                    step.status = StepStatus.FAILED
                    step.error = f"{type(exc).__name__}: {exc}"
                    logger.warning(
                        "DeepAgent step %s failed after %d retries: %s",
                        step.id,
                        step.retry_count,
                        exc,
                    )
                else:
                    logger.info(
                        "DeepAgent step %s retry %d/%d: %s",
                        step.id,
                        step.retry_count,
                        step.max_retries,
                        exc,
                    )

        step.duration_ms = (time.perf_counter() - t0) * 1000.0
        self._execution_log.append(
            {
                "step_id": step.id,
                "tool": step.tool_name,
                "status": step.status.value,
                "duration_ms": step.duration_ms,
                "timestamp": datetime.now(UTC).isoformat(),
                "had_memory_hit": memory_hit is not None,
            }
        )
        return step

    async def aexecute_step(self, step: TaskStep) -> TaskStep:
        """Execute a single step asynchronously."""
        if step.tool_name is None:
            step.status = StepStatus.SKIPPED
            return step

        executor = self._async_tool_executor or self._tool_executor
        if executor is None:
            step.status = StepStatus.SKIPPED
            step.error = "No executor available"
            return step

        step.status = StepStatus.RUNNING
        t0 = time.perf_counter()

        while step.retry_count <= step.max_retries:
            try:
                result = executor(step.tool_name, step.tool_args)
                if asyncio.iscoroutine(result):
                    result = await result
                if self._should_offload(result):
                    result = self._offload_result(step, result)
                step.result = result
                step.status = StepStatus.COMPLETED
                step.completed_at = datetime.now(UTC).isoformat()
                break
            except Exception as exc:
                step.retry_count += 1
                if step.retry_count > step.max_retries:
                    step.status = StepStatus.FAILED
                    step.error = f"{type(exc).__name__}: {exc}"

        step.duration_ms = (time.perf_counter() - t0) * 1000.0
        self._execution_log.append(
            {
                "step_id": step.id,
                "tool": step.tool_name,
                "status": step.status.value,
                "duration_ms": step.duration_ms,
            }
        )
        return step

    def _resolve_dependencies(self, plan: TaskPlan) -> list[TaskStep]:
        """Resolve step dependencies and return ready steps."""
        completed_ids = {s.id for s in plan.steps if s.status == StepStatus.COMPLETED}
        ready = []
        for step in plan.steps:
            if step.status != StepStatus.PENDING:
                continue
            if all(dep in completed_ids for dep in step.depends_on):
                ready.append(step)
            elif any(any(s.id == dep and s.status == StepStatus.FAILED for s in plan.steps) for dep in step.depends_on):
                step.status = StepStatus.BLOCKED
                step.error = "Dependency failed"
        return ready

    def _checkpoint_plan(self, plan: TaskPlan) -> None:
        """Create a checkpoint hash to detect context rot."""
        checkpoint_data = json.dumps(plan.to_checkpoint(), sort_keys=True, ensure_ascii=False)
        checkpoint_hash = hashlib.sha256(checkpoint_data.encode()).hexdigest()[:16]
        plan.checkpoint_hashes.append(checkpoint_hash)
        logger.debug("DeepAgent checkpoint: %s (progress: %s)", checkpoint_hash, f"{plan.progress_ratio:.0%}")

    def execute_plan(self, plan: TaskPlan) -> TaskPlan:
        """Execute a complete plan with dependency resolution."""
        plan.status = StepStatus.RUNNING
        executed = 0
        if self._config.enable_work_bus:
            _publish_work_bus_event_nowait(plan, "plan_started")

        # Priority-sorted execution
        plan.steps.sort(key=lambda s: list(StepPriority).index(s.priority))

        while executed < self._config.max_steps:
            ready = self._resolve_dependencies(plan)
            if not ready:
                break

            step = ready[0]  # Sequential: take highest priority ready step
            if self._config.enable_work_bus:
                _publish_work_bus_event_nowait(plan, "step_started", step)
            self.execute_step(step)
            if self._config.enable_work_bus:
                _publish_work_bus_event_nowait(plan, _step_kind(step), step)
            executed += 1

            # Periodic checkpoint (ECC context rot prevention)
            if executed % self._config.checkpoint_interval == 0:
                self._checkpoint_plan(plan)

            if step.status == StepStatus.FAILED:
                logger.warning("DeepAgent: step %s failed, continuing...", step.id)

        # Final checkpoint
        self._checkpoint_plan(plan)

        # Determine overall status
        if all(s.status in (StepStatus.FAILED, StepStatus.BLOCKED) for s in plan.steps if s.status != StepStatus.SKIPPED):
            plan.status = StepStatus.FAILED
        elif plan.pending_steps or plan.blocked_steps:
            plan.status = StepStatus.RUNNING
        else:
            plan.status = StepStatus.COMPLETED
            plan.completed_at = datetime.now(UTC).isoformat()

        if self._config.enable_skill_solidification:
            self._solidification.maybe_solidify(plan)
        if self._config.enable_work_bus:
            _publish_work_bus_event_nowait(
                plan,
                "plan_completed" if plan.status == StepStatus.COMPLETED else "plan_failed",
            )

        return plan

    async def aexecute_plan(self, plan: TaskPlan) -> TaskPlan:
        """Execute a plan with parallel step support (sub-agent delegation)."""
        plan.status = StepStatus.RUNNING
        executed = 0
        if self._config.enable_work_bus:
            await _publish_work_bus_event(plan, "plan_started")

        while executed < self._config.max_steps:
            ready = self._resolve_dependencies(plan)
            if not ready:
                break

            if self._config.enable_parallel and len(ready) > 1:
                # Parallel execution (deepagents sub-agent pattern)
                batch = ready[: self._config.max_parallel]
                tasks = [self._aexecute_step_with_bus(plan, s) for s in batch]
                await asyncio.gather(*tasks, return_exceptions=True)
                executed += len(batch)
            else:
                await self._aexecute_step_with_bus(plan, ready[0])
                executed += 1

            if executed % self._config.checkpoint_interval == 0:
                self._checkpoint_plan(plan)

        self._checkpoint_plan(plan)

        if all(s.status in (StepStatus.FAILED, StepStatus.BLOCKED) for s in plan.steps if s.status != StepStatus.SKIPPED):
            plan.status = StepStatus.FAILED
        elif plan.pending_steps or plan.blocked_steps:
            plan.status = StepStatus.RUNNING
        else:
            plan.status = StepStatus.COMPLETED
            plan.completed_at = datetime.now(UTC).isoformat()

        if self._config.enable_skill_solidification:
            await asyncio.to_thread(self._solidification.maybe_solidify, plan)
        if self._config.enable_work_bus:
            await _publish_work_bus_event(
                plan,
                "plan_completed" if plan.status == StepStatus.COMPLETED else "plan_failed",
            )

        return plan

    async def _aexecute_step_with_bus(self, plan: TaskPlan, step: TaskStep) -> TaskStep:
        if self._config.enable_work_bus:
            await _publish_work_bus_event(plan, "step_started", step)
        result = await self.aexecute_step(step)
        if self._config.enable_work_bus:
            await _publish_work_bus_event(plan, _step_kind(result), result)
        return result

    def learn(self, fact: str, *, source: str = "execution", tags: list[str] | None = None) -> None:
        """Store a learned fact in session memory."""
        self._memory.add(fact, source=source, tags=tags)
        logger.debug("DeepAgent learned: %s", fact[:100])

    def cleanup_context(self, max_age_hours: int = 24) -> int:
        """Clean up old context files (memory reclamation)."""
        if self._context_store is None:
            return 0
        return self._context_store.cleanup(max_age_hours=max_age_hours)

    @property
    def execution_log(self) -> list[dict[str, Any]]:
        return list(self._execution_log)


# ============================================================
# Skill System (deepagents skills pattern)
# ============================================================


@dataclass
class Skill:
    """A reusable behavior the agent can load on demand.

    Inspired by deepagents skills system: pre-built patterns
    that can be composed into execution plans.
    """

    name: str
    description: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_plan_steps(self, context: dict[str, Any] | None = None) -> list[TaskStep]:
        """Convert skill steps to TaskStep instances."""
        result = []
        for step_def in self.steps:
            tool_args = dict(step_def.get("tool_args", {}))
            # Substitute context variables
            if context:
                for key, value in tool_args.items():
                    if isinstance(value, str) and value.startswith("$"):
                        var_name = value[1:]
                        if var_name in context:
                            tool_args[key] = context[var_name]
            result.append(
                TaskStep(
                    description=step_def.get("description", ""),
                    tool_name=step_def.get("tool_name"),
                    tool_args=tool_args,
                    priority=StepPriority(step_def.get("priority", "normal")),
                )
            )
        return result


class SkillRegistry:
    """Registry of available skills."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def search(self, query: str) -> list[Skill]:
        query_lower = query.lower()
        return [s for s in self._skills.values() if query_lower in s.name.lower() or query_lower in s.description.lower() or any(query_lower in t.lower() for t in s.tags)]

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())


# ============================================================
# Process-global singletons
# ============================================================


_skill_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry


__all__ = [
    "AgentRole",
    "ContextFileStore",
    "DeepAgentConfig",
    "DeepAgentExecutor",
    "MemoryEntry",
    "MemoryStore",
    "SelfSolidificationExecutor",
    "Skill",
    "SkillRegistry",
    "StepPriority",
    "StepStatus",
    "TaskPlan",
    "TaskStep",
    "get_skill_registry",
]
