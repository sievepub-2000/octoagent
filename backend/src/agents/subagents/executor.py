"""Compatibility facade for the unified subagent runtime service."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from langchain.tools import BaseTool

from src.agents.thread_state import SandboxState, ThreadDataState
from src.agents.subagents.config import SubagentConfig

from .contracts import SubagentResult, SubagentStatus
from .service import get_subagent_service

logger = logging.getLogger(__name__)


class SubagentExecutor:
    """Compatibility wrapper that delegates job execution to the unified service."""

    def __init__(
        self,
        config: SubagentConfig,
        tools: list[BaseTool],
        parent_model: str | None = None,
        sandbox_state: SandboxState | None = None,
        thread_data: ThreadDataState | None = None,
        thread_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.config = config
        self.tools = tools
        self.parent_model = parent_model
        self.sandbox_state = sandbox_state
        self.thread_data = thread_data
        self.thread_id = thread_id
        self.trace_id = trace_id or str(uuid.uuid4())[:8]

    async def _aexecute(
        self,
        task: str,
        result_holder: SubagentResult | None = None,
    ) -> SubagentResult:
        service = get_subagent_service()
        task_id = result_holder.task_id if result_holder is not None else str(uuid.uuid4())[:8]
        service.submit_job(
            config=self.config,
            tools=self.tools,
            task=task,
            task_id=task_id,
            parent_model=self.parent_model,
            sandbox_state=self.sandbox_state,
            thread_data=self.thread_data,
            thread_id=self.thread_id,
            trace_id=self.trace_id,
        )
        result = service.wait_for_terminal(task_id, self.config.timeout_seconds + 5)
        if result is None:
            return SubagentResult(
                task_id=task_id,
                trace_id=self.trace_id,
                status=SubagentStatus.FAILED,
                error="Subagent result disappeared from runtime store",
                completed_at=datetime.now(),
            )
        if result_holder is not None:
            result_holder.status = result.status
            result_holder.result = result.result
            result_holder.error = result.error
            result_holder.started_at = result.started_at
            result_holder.completed_at = result.completed_at
            result_holder.ai_messages = result.ai_messages
            return result_holder
        return result

    def execute(
        self,
        task: str,
        result_holder: SubagentResult | None = None,
    ) -> SubagentResult:
        import asyncio

        return asyncio.run(self._aexecute(task, result_holder))

    def execute_async(self, task: str, task_id: str | None = None) -> str:
        task_id = task_id or str(uuid.uuid4())[:8]
        get_subagent_service().submit_job(
            config=self.config,
            tools=self.tools,
            task=task,
            task_id=task_id,
            parent_model=self.parent_model,
            sandbox_state=self.sandbox_state,
            thread_data=self.thread_data,
            thread_id=self.thread_id,
            trace_id=self.trace_id,
        )
        return task_id


def get_background_task_result(task_id: str) -> SubagentResult | None:
    return get_subagent_service().get_job(task_id)


def list_background_tasks() -> list[SubagentResult]:
    return get_subagent_service().list_jobs()


def cleanup_background_task(task_id: str) -> None:
    cleaned = get_subagent_service().cleanup_job(task_id)
    if not cleaned:
        logger.debug("Skipped cleanup for background task %s", task_id)


def get_background_task_events(task_id: str) -> list[dict[str, Any]]:
    return [
        {
            "sequence": event.sequence,
            "type": event.event_type,
            "status": event.status.value,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        }
        for event in get_subagent_service().consume_events(task_id)
    ]


def cancel_background_task(task_id: str) -> bool:
    return get_subagent_service().cancel_job(task_id)


def get_subagent_runtime_snapshot() -> dict[str, int | float | None | dict | list]:
    return get_subagent_service().get_runtime_snapshot()
