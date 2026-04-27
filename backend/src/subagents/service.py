"""Unified runtime service for delegated subagent jobs."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from langchain.agents import create_agent
from langchain.tools import BaseTool
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.thread_state import SandboxState, ThreadDataState, ThreadState
from src.models import create_chat_model
from src.subagents.config import SubagentConfig

from .contracts import SubagentEvent, SubagentResult, SubagentStatus
from .policy import check_admission, estimate_available_memory_gb
from .store import SubagentJobStore

logger = logging.getLogger(__name__)


def _filter_tools(
    all_tools: list[BaseTool],
    allowed: list[str] | None,
    disallowed: list[str] | None,
) -> list[BaseTool]:
    filtered = all_tools
    if allowed is not None:
        allowed_set = set(allowed)
        filtered = [tool for tool in filtered if tool.name in allowed_set]
    if disallowed is not None:
        disallowed_set = set(disallowed)
        filtered = [tool for tool in filtered if tool.name not in disallowed_set]
    return filtered


class SubagentService:
    """Single runtime owner for delegated subagent jobs."""

    def __init__(self) -> None:
        self._store = SubagentJobStore()
        self._execution_pool: ThreadPoolExecutor | None = None
        self._pool_lock = threading.Lock()

    def _ensure_pool(self) -> ThreadPoolExecutor:
        with self._pool_lock:
            if self._execution_pool is None:
                from src.config.subagents_config import get_subagents_app_config

                max_workers = max(1, get_subagents_app_config().max_concurrent_subagents)
                self._execution_pool = ThreadPoolExecutor(
                    max_workers=max_workers,
                    thread_name_prefix="subagent-runtime-",
                )
            return self._execution_pool

    def submit_job(
        self,
        *,
        config: SubagentConfig,
        tools: list[BaseTool],
        task: str,
        task_id: str,
        parent_model: str | None = None,
        sandbox_state: SandboxState | None = None,
        thread_data: ThreadDataState | None = None,
        thread_id: str | None = None,
        trace_id: str | None = None,
    ) -> str:
        trace_id = trace_id or str(uuid.uuid4())[:8]
        existing_jobs = self._store.list()
        rejection_reason = check_admission(existing_jobs, thread_id=thread_id)
        result = SubagentResult(
            task_id=task_id,
            trace_id=trace_id,
            status=SubagentStatus.ADMISSION_REJECTED if rejection_reason else SubagentStatus.QUEUED,
            thread_id=thread_id,
            agent_name=config.name,
            queue_started_at=datetime.now(),
        )
        self._store.create(result)
        if rejection_reason is None:
            self._emit(task_id, trace_id, "job.queued", SubagentStatus.QUEUED, {"agent_name": config.name})
        if rejection_reason is not None:
            self._store.update(
                task_id,
                status=SubagentStatus.ADMISSION_REJECTED,
                error=rejection_reason,
                rejection_reason=rejection_reason,
                completed_at=datetime.now(),
                queue_completed_at=datetime.now(),
            )
            self._emit(task_id, trace_id, "job.rejected", SubagentStatus.ADMISSION_REJECTED, {"reason": rejection_reason})
            return task_id

        self._ensure_pool().submit(
            self._run_job_sync,
            task_id,
            trace_id,
            config,
            tools,
            task,
            parent_model,
            sandbox_state,
            thread_data,
            thread_id,
        )
        return task_id

    def _emit(
        self,
        job_id: str,
        trace_id: str,
        event_type: str,
        status: SubagentStatus,
        payload: dict[str, Any] | None = None,
    ) -> None:
        current = self._store.get(job_id)
        sequence = current.event_count + 1 if current is not None else 1
        self._store.append_event(
            SubagentEvent(
                sequence=sequence,
                job_id=job_id,
                event_type=event_type,
                status=status,
                payload=payload or {"trace_id": trace_id},
            )
        )

    def _create_agent(
        self,
        *,
        config: SubagentConfig,
        tools: list[BaseTool],
        parent_model: str | None,
    ):
        model_name = parent_model if config.model == "inherit" else config.model
        model = create_chat_model(name=model_name, thinking_enabled=False)
        from src.agents.middlewares.thread_data_middleware import ThreadDataMiddleware
        from src.sandbox.middleware import SandboxMiddleware

        middlewares = [
            ThreadDataMiddleware(lazy_init=True),
            SandboxMiddleware(lazy_init=True),
        ]
        return create_agent(
            model=model,
            tools=_filter_tools(tools, config.tools, config.disallowed_tools),
            middleware=middlewares,
            system_prompt=config.system_prompt,
            state_schema=ThreadState,
        )

    def _build_initial_state(
        self,
        *,
        task: str,
        sandbox_state: SandboxState | None,
        thread_data: ThreadDataState | None,
    ) -> dict[str, Any]:
        state: dict[str, Any] = {"messages": [HumanMessage(content=task)]}
        if sandbox_state is not None:
            state["sandbox"] = sandbox_state
        if thread_data is not None:
            state["thread_data"] = thread_data
        return state

    async def _run_agent_async(
        self,
        *,
        job_id: str,
        trace_id: str,
        config: SubagentConfig,
        tools: list[BaseTool],
        task: str,
        parent_model: str | None,
        sandbox_state: SandboxState | None,
        thread_data: ThreadDataState | None,
        thread_id: str | None,
    ) -> SubagentResult:
        started_at = datetime.now()
        self._store.update(
            job_id,
            status=SubagentStatus.STARTING,
            started_at=started_at,
            queue_completed_at=started_at,
        )
        self._emit(job_id, trace_id, "job.started", SubagentStatus.STARTING, {"agent_name": config.name})
        agent = self._create_agent(config=config, tools=tools, parent_model=parent_model)
        state = self._build_initial_state(task=task, sandbox_state=sandbox_state, thread_data=thread_data)

        run_config: RunnableConfig = {"recursion_limit": config.max_turns}
        context: dict[str, Any] = {}
        if thread_id:
            run_config["configurable"] = {"thread_id": thread_id}
            context["thread_id"] = thread_id

        final_state = None
        ai_messages: list[dict[str, Any]] = []
        self._store.update(job_id, status=SubagentStatus.RUNNING)
        self._emit(job_id, trace_id, "job.running", SubagentStatus.RUNNING, {"max_turns": config.max_turns})

        async for chunk in agent.astream(state, config=run_config, context=context, stream_mode="values"):  # type: ignore[arg-type]
            if self._store.is_cancel_requested(job_id):
                raise asyncio.CancelledError(f"Subagent job {job_id} was cancelled")
            final_state = chunk
            messages = chunk.get("messages", [])
            if not messages:
                continue
            last_message = messages[-1]
            if isinstance(last_message, AIMessage):
                message_dict = last_message.model_dump(exclude={"context"})
                message_id = message_dict.get("id")
                duplicate = False
                if message_id:
                    duplicate = any(item.get("id") == message_id for item in ai_messages)
                else:
                    duplicate = message_dict in ai_messages
                if not duplicate:
                    ai_messages.append(message_dict)
                    self._store.update(job_id, status=SubagentStatus.STREAMING, ai_messages=ai_messages)
                    self._emit(
                        job_id,
                        trace_id,
                        "job.message",
                        SubagentStatus.STREAMING,
                        {"message_index": len(ai_messages), "message": message_dict},
                    )

        result_text = "No response generated"
        if final_state is not None:
            messages = final_state.get("messages", [])
            last_ai_message = next((msg for msg in reversed(messages) if isinstance(msg, AIMessage)), None)
            if last_ai_message is not None:
                content = last_ai_message.content
                if isinstance(content, str):
                    result_text = content
                elif isinstance(content, list):
                    text_parts: list[str] = []
                    for block in content:
                        if isinstance(block, str):
                            text_parts.append(block)
                        elif isinstance(block, dict) and "text" in block:
                            text_parts.append(block["text"])
                    if text_parts:
                        result_text = "\n".join(text_parts)

        completed_at = datetime.now()
        snapshot = self._store.update(
            job_id,
            status=SubagentStatus.COMPLETED,
            result=result_text,
            completed_at=completed_at,
            ai_messages=ai_messages,
        )
        self._emit(job_id, trace_id, "job.completed", SubagentStatus.COMPLETED, {"result": result_text})
        assert snapshot is not None
        return snapshot

    async def _run_agent_with_timeout(self, **kwargs: Any) -> SubagentResult:
        timeout_seconds = kwargs["config"].timeout_seconds
        try:
            return await asyncio.wait_for(self._run_agent_async(**kwargs), timeout=timeout_seconds)
        except TimeoutError:
            job_id = kwargs["job_id"]
            trace_id = kwargs["trace_id"]
            result = self._store.update(
                job_id,
                status=SubagentStatus.TIMED_OUT,
                error=f"Execution timed out after {timeout_seconds} seconds",
                completed_at=datetime.now(),
            )
            self._emit(job_id, trace_id, "job.timed_out", SubagentStatus.TIMED_OUT, {"timeout_seconds": timeout_seconds})
            assert result is not None
            return result
        except asyncio.CancelledError as exc:
            job_id = kwargs["job_id"]
            trace_id = kwargs["trace_id"]
            result = self._store.update(
                job_id,
                status=SubagentStatus.CANCELLED,
                error=str(exc),
                completed_at=datetime.now(),
            )
            self._emit(job_id, trace_id, "job.cancelled", SubagentStatus.CANCELLED, {})
            assert result is not None
            return result
        except Exception as exc:
            logger.exception("[trace=%s] Subagent %s execution failed", kwargs["trace_id"], kwargs["config"].name)
            job_id = kwargs["job_id"]
            trace_id = kwargs["trace_id"]
            result = self._store.update(
                job_id,
                status=SubagentStatus.FAILED,
                error=str(exc),
                completed_at=datetime.now(),
            )
            self._emit(job_id, trace_id, "job.failed", SubagentStatus.FAILED, {"error": str(exc)})
            assert result is not None
            return result

    def _run_job_sync(
        self,
        job_id: str,
        trace_id: str,
        config: SubagentConfig,
        tools: list[BaseTool],
        task: str,
        parent_model: str | None,
        sandbox_state: SandboxState | None,
        thread_data: ThreadDataState | None,
        thread_id: str | None,
    ) -> None:
        asyncio.run(
            self._run_agent_with_timeout(
                job_id=job_id,
                trace_id=trace_id,
                config=config,
                tools=tools,
                task=task,
                parent_model=parent_model,
                sandbox_state=sandbox_state,
                thread_data=thread_data,
                thread_id=thread_id,
            )
        )

    def get_job(self, job_id: str) -> SubagentResult | None:
        return self._store.get(job_id)

    def list_jobs(self) -> list[SubagentResult]:
        return self._store.list()

    def wait_for_terminal(self, job_id: str, timeout_seconds: float) -> SubagentResult | None:
        return self._store.wait_for_terminal(job_id, timeout_seconds)

    def cancel_job(self, job_id: str) -> bool:
        return self._store.request_cancel(job_id)

    def cleanup_job(self, job_id: str) -> bool:
        return self._store.cleanup(job_id)

    def consume_events(self, job_id: str) -> list[SubagentEvent]:
        return self._store.pop_events(job_id)

    def get_runtime_snapshot(self) -> dict[str, Any]:
        jobs = self._store.list()
        by_status: dict[str, int] = {}
        by_thread: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        timed_out_count = 0
        rejected_count = 0
        recent_failures: list[dict[str, str]] = []
        for item in jobs:
            by_status[item.status.value] = by_status.get(item.status.value, 0) + 1
            if item.thread_id:
                by_thread[item.thread_id] = by_thread.get(item.thread_id, 0) + 1
            if item.agent_name:
                by_agent[item.agent_name] = by_agent.get(item.agent_name, 0) + 1
            if item.status == SubagentStatus.TIMED_OUT:
                timed_out_count += 1
            if item.status == SubagentStatus.ADMISSION_REJECTED:
                rejected_count += 1
            if item.status in {SubagentStatus.FAILED, SubagentStatus.TIMED_OUT, SubagentStatus.ADMISSION_REJECTED} and item.error:
                recent_failures.append(
                    {
                        "task_id": item.task_id,
                        "status": item.status.value,
                        "error": item.error,
                    }
                )
        return {
            "active_subagents": sum(by_status.get(status.value, 0) for status in (SubagentStatus.QUEUED, SubagentStatus.STARTING, SubagentStatus.RUNNING, SubagentStatus.STREAMING, SubagentStatus.CANCEL_REQUESTED)),
            "available_memory_gb": estimate_available_memory_gb(),
            "jobs_by_status": by_status,
            "thread_active_counts": by_thread,
            "jobs_by_agent": by_agent,
            "timed_out_count": timed_out_count,
            "rejected_count": rejected_count,
            "recent_failures": recent_failures[-10:],
        }


_subagent_service: SubagentService | None = None


def get_subagent_service() -> SubagentService:
    global _subagent_service
    if _subagent_service is None:
        _subagent_service = SubagentService()
    return _subagent_service
