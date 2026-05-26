"""LangGraph-backed runtime adapter."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from typing import Any

from langgraph_sdk import get_client

from src.agents.runtime.langgraph_remote import normalize_remote_run_payload
from src.agents.runtime.workflow_contract import get_langgraph_workflow_contract_service
from src.runtime.governance import get_runtime_worker_isolation

from ..contracts import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentRuntimeExecutionSnapshot,
    AgentRuntimeProviderContract,
)

logger = logging.getLogger(__name__)
_DEFAULT_ASSISTANT_ID = "lead_agent"
_CONFIG_AGENT_NAME_RE = re.compile(r"^[A-Za-z0-9-]+$")


def _langgraph_base_url() -> str:
    return os.getenv("OCTO_LANGGRAPH_BASE_URL", "http://localhost:19884")


def _read_hint(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _workspace_hint(metadata: Mapping[str, Any] | None, *keys: str) -> str | None:
    if not isinstance(metadata, Mapping):
        return None
    for key in keys:
        value = _read_hint(metadata.get(key))
        if value is not None:
            return value
    return None


def _resolve_assistant_id(request: AgentExecutionRequest) -> str:
    return _read_hint(request.assistant_id) or _workspace_hint(request.workspace_metadata, "langgraph_assistant_id") or _DEFAULT_ASSISTANT_ID


def _resolve_graph_id(request: AgentExecutionRequest) -> str | None:
    return _read_hint(request.graph_id) or _workspace_hint(
        request.workspace_metadata,
        "langgraph_graph_id",
        "compiled_graph_id",
    )


def _resolve_thread_id(request: AgentExecutionRequest) -> str | None:
    return _read_hint(request.thread_id) or _workspace_hint(
        request.workspace_metadata,
        "langgraph_thread_id",
        "runtime_session_id",
        "last_runtime_session_id",
    )


def _resolve_config_agent_name(request: AgentExecutionRequest) -> str | None:
    agent_name = _read_hint(request.agent_name)
    if agent_name is None:
        return None
    if _CONFIG_AGENT_NAME_RE.fullmatch(agent_name):
        return agent_name
    return None


class LangGraphRuntimeProvider:
    name = "langgraph"

    def is_sdk_available(self) -> bool:
        return True

    def get_sdk_info(self) -> dict[str, object]:
        return {
            "package": "langgraph_sdk",
            "base_url": _langgraph_base_url(),
            "sdk_available": True,
        }

    def get_contract(self) -> AgentRuntimeProviderContract:
        return AgentRuntimeProviderContract(
            provider=self.name,
            runtime_kind="remote_graph",
            session_identifier_kind="thread_id",
            execution_target_kind="assistant_or_graph",
            tool_runtime_contract="langgraph_context",
            supports_subagents=True,
            supports_thread_reuse=True,
            sdk_info=self.get_sdk_info(),
        )

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        client = get_client(url=_langgraph_base_url())
        assistant_id = _resolve_assistant_id(request)
        graph_id = _resolve_graph_id(request)
        preferred_thread_id = _resolve_thread_id(request)
        thread_created = False

        if preferred_thread_id is not None:
            tid = preferred_thread_id
        else:
            thread = await client.threads.create()
            tid = thread["thread_id"]
            thread_created = True

        run_context: dict[str, object] = {
            "thread_id": tid,
            "task_id": request.task_id,
            "thinking_enabled": False,
            "subagent_enabled": request.subagent_enabled,
        }
        run_config: dict[str, object] = {
            "metadata": {
                "thinking_enabled": False,
                "subagent_enabled": request.subagent_enabled,
                "assistant_id": assistant_id,
            },
            "configurable": {
                "thinking_enabled": False,
                "subagent_enabled": request.subagent_enabled,
                "assistant_id": assistant_id,
            },
            "recursion_limit": request.recursion_limit,
            "timeout_seconds": request.timeout_seconds,
        }
        if request.agent_id:
            run_context["agent_id"] = request.agent_id
        if request.agent_name:
            run_context["display_agent_name"] = request.agent_name
            run_config["metadata"]["display_agent_name"] = request.agent_name
            run_config["configurable"]["display_agent_name"] = request.agent_name
        config_agent_name = _resolve_config_agent_name(request)
        if config_agent_name:
            run_context["agent_name"] = config_agent_name
            run_config["metadata"]["agent_name"] = config_agent_name
            run_config["configurable"]["agent_name"] = config_agent_name
        if request.agent_role:
            run_context["agent_role"] = request.agent_role
            run_config["metadata"]["agent_role"] = request.agent_role
            run_config["configurable"]["agent_role"] = request.agent_role
        if graph_id:
            run_context["langgraph_graph_id"] = graph_id
            run_config["metadata"]["langgraph_graph_id"] = graph_id
            run_config["configurable"]["langgraph_graph_id"] = graph_id

        for key in ("session_mode", "coordination_strategy", "langgraph_thread_scope"):
            value = _workspace_hint(request.workspace_metadata, key)
            if value is None:
                continue
            run_context[key] = value
            run_config["metadata"][key] = value
            run_config["configurable"][key] = value

        if request.model_override:
            run_config["metadata"]["model_name"] = request.model_override
            run_config["configurable"]["model_name"] = request.model_override
            run_context["model_name"] = request.model_override

        planned_execution_target: str | None = None
        if request.query_session_id:
            # Lazy import to break circular cycle:
            # query_engine.contracts -> agent_runtime -> providers.langgraph -> query_engine.
            from src.storage.query import QueryOperationPlanRequest, get_query_engine_service

            session = get_query_engine_service().get_session(request.query_session_id)
            if session is not None:
                permission_mode = str(session.metadata.get("permission_mode") or "workspace")
                operation_plan = get_query_engine_service().plan_operation(
                    QueryOperationPlanRequest(
                        user_message=request.prompt,
                        current_goal=session.current_goal,
                        permission_mode=permission_mode,
                        archived_turn_count=session.memory_profile.archived_turn_count,
                    )
                )
                planned_execution_target = operation_plan.command.execution_target
                run_context.update(
                    {
                        "query_session_id": session.session_id,
                        "current_goal": session.current_goal,
                        "prompt_stack_profile_id": session.prompt_stack_profile_id,
                        "client_command": operation_plan.command.model_dump(mode="json"),
                        "session_governance": operation_plan.governance.model_dump(mode="json"),
                    }
                )

        run_config, run_context = normalize_remote_run_payload(run_config, run_context)

        # SDK alignment: metadata must be a separate parameter of runs.wait, not inside config.
        # timeout_seconds is not a valid Config field (it is already used in asyncio.wait_for).
        run_metadata: dict | None = run_config.pop("metadata", None)  # type: ignore[assignment]
        run_config.pop("timeout_seconds", None)

        thread_scope = str(request.workspace_metadata.get("langgraph_thread_scope") or "workspace")
        contract_service = get_langgraph_workflow_contract_service()
        contract_run = contract_service.start_run(
            task_id=request.task_id,
            thread_id=tid,
            assistant_id=assistant_id,
            graph_id=graph_id,
            agent_id=request.agent_id,
            query_session_id=request.query_session_id,
            thread_scope=thread_scope,
        )

        try:
            async with get_runtime_worker_isolation().async_slot("model"):
                result = await client.runs.wait(
                    tid,
                    assistant_id=assistant_id,
                    input={"messages": [{"role": "human", "content": request.prompt}]},
                    metadata=run_metadata,
                    config=run_config,
                    context=run_context,
                )
        except Exception as exc:
            contract_service.finish_run(
                thread_id=tid,
                run_id=contract_run.run_id,
                status="failed",
                error=str(exc),
            )
            logger.exception(
                "LangGraph run failed for task %s (thread=%s, assistant=%s)",
                request.task_id,
                tid,
                assistant_id,
            )
            raise RuntimeError(f"LangGraph execution failed (thread={tid}, assistant={assistant_id}): {exc}") from exc
        # runs.wait returns dict[str, Any] for state-based graphs but can also
        # return list[dict] for stateless or multi-value outputs.  Handle both.
        result_msgs = result.get("messages", []) if isinstance(result, dict) else []
        tool_call_count = 0
        tool_result_count = 0
        for message in result_msgs:
            raw_tool_calls = message.get("tool_calls")
            if isinstance(raw_tool_calls, list):
                tool_call_count += len(raw_tool_calls)
            if message.get("type") == "tool":
                tool_result_count += 1
        effective_tool_call_count = max(tool_call_count, tool_result_count)
        contract_service.finish_run(
            thread_id=tid,
            run_id=contract_run.run_id,
            status="completed",
            message_count=len(result_msgs),
            tool_call_count=effective_tool_call_count,
        )
        logger.info(
            "LangGraph response for task %s: %d messages, types=%s",
            request.task_id,
            len(result_msgs),
            [
                (
                    message.get("type"),
                    bool(message.get("tool_calls")),
                    type(message.get("content")).__name__,
                    len(str(message.get("content", ""))),
                )
                for message in result_msgs[-5:]
            ],
        )

        output_text: str | None = None

        # Pass 1: Prefer the last AI message that has text but NO tool_calls
        for message in reversed(result_msgs):
            if message.get("type") != "ai" or message.get("tool_calls"):
                continue
            content = message.get("content")
            if isinstance(content, list):
                text_parts = [part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"]
                content = "\n".join(text_parts)
            if content:
                output_text = str(content)
                break

        # Pass 2: Some models put text in AI messages that also carry tool_calls;
        # check those if Pass 1 found nothing.
        if output_text is None:
            for message in reversed(result_msgs):
                if message.get("type") != "ai":
                    continue
                content = message.get("content")
                if isinstance(content, list):
                    text_parts = [part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"]
                    content = "\n".join(text_parts)
                if content:
                    output_text = str(content)
                    break

        # Pass 3: Fall back to tool-result messages (the actual work output).
        if output_text is None:
            tool_contents: list[str] = []
            for message in result_msgs:
                if message.get("type") == "tool":
                    tc = message.get("content")
                    if isinstance(tc, str) and tc.strip():
                        tool_contents.append(tc.strip())
            if tool_contents:
                output_text = "\n\n".join(tool_contents[-3:])  # last 3 tool results

        if planned_execution_target is None:
            planned_execution_target = graph_id or assistant_id

        return AgentExecutionResult(
            provider=self.name,
            output_text=output_text,
            message_count=len(result_msgs),
            tool_call_count=effective_tool_call_count,
            thread_id=tid,
            planned_execution_target=planned_execution_target,
            runtime_snapshot=AgentRuntimeExecutionSnapshot(
                provider=self.name,
                session_id=tid,
                execution_target=planned_execution_target,
                message_count=len(result_msgs),
                tool_call_count=effective_tool_call_count,
                model_name=request.model_override,
                metadata={
                    "assistant_id": assistant_id,
                    "graph_id": graph_id,
                    "thread_created": thread_created,
                    "run_id": contract_run.run_id,
                    "thread_scope": thread_scope,
                },
            ),
            raw={
                "assistant_id": assistant_id,
                "graph_id": graph_id,
                "thread_id": tid,
                "thread_created": thread_created,
                "run_id": contract_run.run_id,
                "messages": result_msgs,
            },
        )
