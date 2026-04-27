"""Task workspace execution policy and controller helpers."""

from __future__ import annotations

import datetime
import logging
from collections.abc import Awaitable, Callable
from typing import Any

# Slice F: canonical definitions now live in agent_core; re-export for compat.
from src.agent_core.execution_policies import (  # noqa: F401
    _FAILURE_MARKERS,
    _HARD_FAILURE_MARKERS,
    _MAX_AGENT_RETRIES,
    _RESEARCH_HINT_MARKERS,
    agent_supports_subagent_delegation,
    evaluate_task_outcome,
    extract_expected_keywords,
    get_escalation_stage,
    get_execution_retry_budget,
    looks_like_ai_model_news_query,
    normalize_text,
    output_indicates_hard_failure,
    requires_tool_backed_research,
    resolve_execution_roles,
)
from src.agent_core.prompts import (  # noqa: F401
    build_final_synthesis_prompt,
    build_lead_agent_prompt,
    build_lead_direct_execution_prompt,
    build_lead_optimization_plan_prompt,
    build_multi_agent_kickoff_prompt,
    build_reviewer_prompt,
    build_worker_prompt,
    build_worker_self_analysis_prompt,
    build_worker_stage2_prompt,
    build_worker_takeover_prompt,
    build_worker_timeout_analysis_prompt,
    format_transcript_messages,
)
from src.agent_core.session import (
    mark_query_session_running,
    record_query_agent_execution,
    resolve_query_session_id,
)

from .contracts import AgentHandle, AgentMessage, CreateAgentMessageRequest, TaskWorkspace, utc_now
from .execution_runtime_helpers import (
    execute_agent_step,
    execute_worker_with_timeout_recovery,
    run_direct_model_fallback,
)
from .research_fallback import build_server_side_research_fallback

logger = logging.getLogger(__name__)

_X_DOMAIN_MARKERS = ("x.com", "twitter", "site:x.com")
_SINA_DOMAIN_MARKERS = ("新浪", "sina", "news.sina.com.cn")
_NEWS_QUERY_MARKERS = ("news", "headline", "headlines", "新闻", "资讯", "头条")
_TOP_NEWS_QUERY_MARKERS = ("top 10", "top10", "top ten", "前十", "前10", "十大", "热点", "热榜")

_TASK_GOAL_PROMPT_MARKERS = (
    "原始任务目标：",
    "任务目标：",
    "总任务：",
    "负责核查以下任务是否真正完成：",
)

_TASK_PROMPT_SECTION_MARKERS = (
    "执行成员：",
    "协调者要求：",
    "其他已完成 worker 输出：",
    "待核查 worker 输出：",
    "协调计划：",
    "worker 输出：",
    "review 结论：",
)


def _prefers_server_side_ai_news_fallback(query: str | None) -> bool:
    normalized = normalize_text(query)
    return looks_like_ai_model_news_query(normalized) and any(marker in normalized for marker in _X_DOMAIN_MARKERS)


def _prefers_server_side_news_fallback(query: str | None) -> bool:
    normalized = normalize_text(query)
    if _prefers_server_side_ai_news_fallback(normalized):
        return True
    mentions_sina = any(marker in normalized for marker in _SINA_DOMAIN_MARKERS)
    mentions_news = any(marker in normalized for marker in _NEWS_QUERY_MARKERS)
    mentions_top_news = any(marker in normalized for marker in _TOP_NEWS_QUERY_MARKERS)
    return mentions_sina and mentions_news and mentions_top_news


def _server_side_fallback_target(query: str | None) -> str:
    if _prefers_server_side_ai_news_fallback(query):
        return "server_side_ai_news_fallback"
    if _prefers_server_side_news_fallback(query):
        return "server_side_news_fallback"
    return "server_side_research_fallback"


class TaskWorkspaceExecutionController:
    """Own workspace execution retry orchestration."""

    def __init__(self):
        self._inflight_tasks: set[str] = set()

    async def auto_execute_workspace(
        self,
        workspace: TaskWorkspace,
        *,
        send_message: Callable[[str, str, CreateAgentMessageRequest], Awaitable[Any]],
        service,
        merge_workspace_metadata: Callable[..., TaskWorkspace | None],
        workflow_module_factory,
    ) -> None:
        import asyncio

        from src.agent_core.service import get_agent_core_service

        lead_agent, worker_agents, review_agent = resolve_execution_roles(workspace)
        agent_core = get_agent_core_service()
        sub_agents = [agent for agent in workspace.agents if agent.agent_id != lead_agent.agent_id]
        sub_agent_names = [agent.name or agent.role for agent in sub_agents]
        goal = workspace.goal or workspace.name
        execution_start = datetime.datetime.now(datetime.UTC)
        agent_core.begin_workspace_execution(
            workspace.task_id,
            lead_agent_id=lead_agent.agent_id,
            task_service=service,
        )

        ws_timeout = 360 if workspace.mode in {"group", "branch"} else 240
        if workspace.metadata and workspace.metadata.get("timeout_seconds"):
            ws_timeout = min(int(workspace.metadata["timeout_seconds"]), 7200)
        per_attempt_timeout = max(60, min(ws_timeout + 30, 900))
        retry_budget = get_execution_retry_budget(workspace)
        workflow_module = workflow_module_factory()

        evaluated_status = "failed"
        failure_reason: str | None = None
        last_output = ""
        all_transcripts: list[str] = []

        # 3-3-6 escalation state
        failure_history: list[dict[str, Any]] = []
        stage2_optimization_plan: str = ""

        for attempt in range(1, retry_budget + 1):
            attempt_start = datetime.datetime.now(datetime.UTC)
            stage = get_escalation_stage(attempt)

            # Determine prompt per stage (only applied to mode=single; multi-agent
            # flow already has its own kickoff/synthesis pipeline below).
            if stage == 3:
                # Stage 3: lead takes over directly
                round_prompt = build_lead_direct_execution_prompt(goal, failure_history)
            elif stage == 2:
                # Stage 2 (attempts 4-6): lead-provided plan, subagent executes
                if not stage2_optimization_plan:
                    plan_prompt = build_lead_optimization_plan_prompt(
                        goal,
                        failure_history,
                        sub_agent_name=sub_agent_names[0] if sub_agent_names else None,
                    )
                    try:
                        request = CreateAgentMessageRequest(
                            content=plan_prompt, model_override=lead_agent.model_name
                        )
                        plan_response = await asyncio.wait_for(
                            send_message(workspace.task_id, lead_agent.agent_id, request),
                            timeout=per_attempt_timeout,
                        )
                        for msg in plan_response.messages[-3:]:
                            if msg.role == "assistant" and msg.content:
                                stage2_optimization_plan = str(msg.content)
                        all_transcripts.append(
                            "### 阶段二 · 主代理优化方案\n\n"
                            f"**{lead_agent.name} · plan**: "
                            f"{stage2_optimization_plan[:800]}"
                        )
                    except Exception as exc:
                        logger.warning(
                            "Task %s stage2 plan generation failed: %s",
                            workspace.task_id,
                            exc,
                        )
                        stage2_optimization_plan = ""
                round_prompt = build_worker_stage2_prompt(
                    goal,
                    stage2_optimization_plan,
                    attempt_index=attempt,
                    stage1_failures=[h for h in failure_history if h.get("stage") == 1],
                    stage2_failures=[h for h in failure_history if h.get("stage") == 2],
                    agent_name=sub_agent_names[0] if sub_agent_names else None,
                )
            elif attempt >= 2:
                # Stage 1 retries (attempts 2-3): subagent self-analysis
                round_prompt = build_worker_self_analysis_prompt(
                    goal,
                    failure_history,
                    attempt_index=attempt,
                    agent_name=sub_agent_names[0] if sub_agent_names else None,
                )
            else:
                # Stage 1 attempt 1: original kickoff prompt
                round_prompt = build_lead_agent_prompt(
                    workspace, goal, attempt, last_output, failure_reason, sub_agent_names
                )
            attempt_output = ""
            attempt_transcripts: list[str] = []
            attempt_failed = False
            attempt_failure_reason: str | None = None
            try:
                if workspace.mode == "single" or stage == 3:
                    # Stage 3 forces single-agent path (lead takes over directly),
                    # even if the workspace is a multi-agent group.
                    executing_agent = lead_agent
                    request = CreateAgentMessageRequest(content=round_prompt, model_override=executing_agent.model_name)
                    response = await asyncio.wait_for(
                        send_message(workspace.task_id, executing_agent.agent_id, request),
                        timeout=per_attempt_timeout,
                    )
                    for msg in response.messages[-3:]:
                        attempt_transcripts.append(f"**{executing_agent.name} · {msg.role}**: {str(msg.content)[:600]}")
                        if msg.role == "assistant" and msg.content:
                            attempt_output = str(msg.content)
                else:
                    attempt_output, attempt_transcripts = await self._run_multi_agent_attempt(
                        workspace=workspace,
                        goal=goal,
                        attempt=attempt,
                        last_output=last_output,
                        last_failure_reason=failure_reason,
                        lead_agent=lead_agent,
                        worker_agents=worker_agents,
                        review_agent=review_agent,
                        send_message=send_message,
                        timeout_seconds=per_attempt_timeout,
                    )
            except TimeoutError:
                attempt_failed = True
                attempt_failure_reason = f"执行超时（超过 {per_attempt_timeout}s 未返回结果）"
            except Exception as exc:
                attempt_failed = True
                attempt_failure_reason = f"执行异常：{exc}"
                logger.exception("Task %s attempt %d raised an exception", workspace.task_id, attempt)

            attempt_elapsed = (datetime.datetime.now(datetime.UTC) - attempt_start).total_seconds()
            if attempt_transcripts:
                all_transcripts.append(
                    f"### 尝试 {attempt}/{retry_budget}（耗时 {attempt_elapsed:.1f}s）\n\n"
                    + "\n\n".join(attempt_transcripts)
                )
            elif attempt_failed:
                all_transcripts.append(
                    f"### 尝试 {attempt}/{retry_budget}（失败，耗时 {attempt_elapsed:.1f}s）\n\n"
                    f"**error**: {attempt_failure_reason}"
                )

            if attempt_failed:
                evaluated_status = "failed"
                failure_reason = attempt_failure_reason
                last_output = attempt_output
            else:
                last_output = attempt_output
                evaluated_status, failure_reason = evaluate_task_outcome(workspace, attempt_output)

            if evaluated_status != "failed":
                await self._complete_execution(
                    workspace=workspace,
                    service=service,
                    merge_workspace_metadata=merge_workspace_metadata,
                    workflow_module=workflow_module,
                    output=attempt_output,
                    transcripts=all_transcripts,
                    execution_start=execution_start,
                    attempt=attempt,
                    retry_budget=retry_budget,
                )
                return

            # Record this failure for escalation context
            failure_history.append(
                {
                    "attempt": attempt,
                    "stage": stage,
                    "reason": failure_reason or "未给出原因",
                    "output": (attempt_output or "")[:400],
                }
            )

            # Allow escalation to reach stage 3 even on hard-failures — the whole
            # point of the 3-3-6 flow is that the lead personally retries after
            # the sub-agent fails repeatedly.  Only break out of the loop when
            # we have already run the final (stage-3) lead-takeover attempt.
            if stage == 3 and (
                output_indicates_hard_failure(attempt_output)
                or output_indicates_hard_failure(failure_reason)
            ):
                break
            if attempt >= retry_budget:
                break

        await self._fail_execution(
            workspace=workspace,
            service=service,
            workflow_module=workflow_module,
            last_output=last_output,
            failure_reason=failure_reason,
            transcripts=all_transcripts,
            execution_start=execution_start,
            retry_budget=retry_budget,
            lead_agent=lead_agent,
        )

    # Deprecated alias — use auto_execute_workspace() instead
    auto_execute_lead_agent = auto_execute_workspace

    async def safe_auto_execute_workspace(
        self,
        workspace: TaskWorkspace,
        *,
        send_message: Callable[[str, str, CreateAgentMessageRequest], Awaitable[Any]],
        service_getter: Callable[[], Any],
        merge_workspace_metadata: Callable[..., TaskWorkspace | None],
        workflow_module_factory,
    ) -> None:
        if workspace.task_id in self._inflight_tasks:
            logger.warning("Task %s already in-flight, skipping duplicate execution", workspace.task_id)
            return
        self._inflight_tasks.add(workspace.task_id)
        try:
            await self.auto_execute_workspace(
                workspace,
                send_message=send_message,
                service=service_getter(),
                merge_workspace_metadata=merge_workspace_metadata,
                workflow_module_factory=workflow_module_factory,
            )
        except Exception as exc:
            logger.exception("Unrecoverable error in auto execution for task %s", workspace.task_id)
            try:
                from src.agent_core.service import get_agent_core_service

                service = service_getter()
                current_ws = service.get_workspace(workspace.task_id)
                agent_ids = [
                    agent.agent_id
                    for agent in (current_ws or workspace).agents
                ]
                current_ws = (
                    get_agent_core_service().terminate_all_agents(
                        workspace.task_id, agent_ids, task_service=service
                    )
                    or current_ws
                    or workspace
                )
                workflow_module_factory().record_execution_result(
                    current_ws,
                    status="failed",
                    output="（执行引擎遭遇不可恢复的异常，任务终止。）",
                    transcripts="（无完整记录。）",
                    failure_reason=str(exc),
                )
            except Exception:
                logger.exception("Failed to persist crash-failed state for task %s", workspace.task_id)
        finally:
            self._inflight_tasks.discard(workspace.task_id)

    # Deprecated alias — use safe_auto_execute_workspace() instead
    safe_auto_execute_lead_agent = safe_auto_execute_workspace

    async def _run_multi_agent_attempt(
        self,
        *,
        workspace: TaskWorkspace,
        goal: str,
        attempt: int,
        last_output: str,
        last_failure_reason: str | None,
        lead_agent: AgentHandle,
        worker_agents: list[AgentHandle],
        review_agent: AgentHandle | None,
        send_message: Callable[[str, str, CreateAgentMessageRequest], Awaitable[Any]],
        timeout_seconds: int,
    ) -> tuple[str, list[str]]:

        kickoff_prompt = build_multi_agent_kickoff_prompt(
            workspace,
            goal,
            worker_agents,
            review_agent,
            attempt,
            last_output,
            last_failure_reason,
        )
        coordinator_output, transcripts = await execute_agent_step(
            workspace.task_id, lead_agent, kickoff_prompt, send_message, timeout_seconds
        )
        worker_outputs: dict[str, str] = {}
        for worker_agent in worker_agents:
            worker_prompt = build_worker_prompt(goal, coordinator_output, worker_agent, worker_outputs)
            worker_output, worker_transcript = await execute_worker_with_timeout_recovery(
                workspace=workspace,
                goal=goal,
                worker_agent=worker_agent,
                initial_prompt=worker_prompt,
                coordinator_output=coordinator_output,
                prior_worker_outputs=worker_outputs,
                send_message=send_message,
                lead_agent=lead_agent,
                timeout_seconds=timeout_seconds,
            )
            worker_outputs[worker_agent.name] = worker_output
            transcripts.extend(worker_transcript)

        review_output = ""
        if review_agent is not None:
            review_prompt = build_reviewer_prompt(goal, worker_outputs)
            review_output, review_transcript = await execute_agent_step(
                workspace.task_id,
                review_agent,
                review_prompt,
                send_message,
                timeout_seconds,
            )
            transcripts.extend(review_transcript)

        final_prompt = build_final_synthesis_prompt(goal, coordinator_output, worker_outputs, review_output)
        attempt_output, final_transcript = await execute_agent_step(
            workspace.task_id,
            lead_agent,
            final_prompt,
            send_message,
            timeout_seconds,
        )
        transcripts.extend(final_transcript)
        return attempt_output, transcripts

    async def _complete_execution(
        self,
        *,
        workspace: TaskWorkspace,
        service,
        merge_workspace_metadata,
        workflow_module,
        output: str,
        transcripts: list[str],
        execution_start,
        attempt: int,
        retry_budget: int,
    ) -> None:
        elapsed_total = (datetime.datetime.now(datetime.UTC) - execution_start).total_seconds()
        from src.agent_core.service import get_agent_core_service

        if workspace.mode in {"branch", "group"}:
            merge_workspace_metadata(
                workspace.task_id,
                review_completed=True,
                review_completed_at=datetime.datetime.now(datetime.UTC).isoformat(),
            )
        agent_ids = [agent.agent_id for agent in workspace.agents]
        current_workspace = (
            get_agent_core_service().complete_all_agents(
                workspace.task_id, agent_ids, task_service=service
            )
            or service.get_workspace(workspace.task_id)
            or workspace
        )
        workflow_module.record_execution_result(
            current_workspace,
            status="completed",
            output=output or "（任务已完成，无文本输出。）",
            transcripts="\n\n".join(transcripts),
            failure_reason=None,
        )
        logger.info(
            "Auto-execution completed for task %s (attempt %d/%d, %.1fs)",
            workspace.task_id,
            attempt,
            retry_budget,
            elapsed_total,
        )

    async def _fail_execution(
        self,
        *,
        workspace: TaskWorkspace,
        service,
        workflow_module,
        last_output: str,
        failure_reason: str | None,
        transcripts: list[str],
        execution_start,
        retry_budget: int,
        lead_agent: AgentHandle,
    ) -> None:
        elapsed_total = (datetime.datetime.now(datetime.UTC) - execution_start).total_seconds()
        from src.agent_core.service import get_agent_core_service

        failure_analysis = (
            f"## 执行失败分析\n\n"
            f"任务在连续 {retry_budget} 次尝试后仍未达到预期结果。\n\n"
            f"**最终失败原因**：{failure_reason or '输出不符合预期'}\n\n"
            f"**总耗时**：{elapsed_total:.1f}s\n\n"
            f"**最后一轮输出**：\n\n"
            f"{(last_output[:1200] + '…') if len(last_output) > 1200 else last_output or '（无文本输出）'}"
        )
        agent_ids = [agent.agent_id for agent in workspace.agents]
        current_workspace = (
            get_agent_core_service().fail_execution(
                workspace.task_id,
                lead_agent_id=lead_agent.agent_id,
                all_agent_ids=agent_ids,
                task_service=service,
            )
            or service.get_workspace(workspace.task_id)
            or workspace
        )
        workflow_module.record_execution_result(
            current_workspace,
            status="failed",
            output=failure_analysis,
            transcripts="\n\n".join(transcripts),
            failure_reason=failure_reason,
        )


class TaskWorkspaceMessageExecutor:
    """Encapsulate workspace-scoped agent message execution policy."""

    async def execute(
        self,
        *,
        task_id: str,
        agent_id: str,
        request: CreateAgentMessageRequest,
        workspace: TaskWorkspace | None,
        invoke_agent_runtime,
        append_message,
    ) -> list[AgentMessage] | None:
        from src.agent_core import get_agent_core_service

        assistant_content: str | None = None
        query_session_id: str | None = None
        execution_target: str | None = None
        runtime_session_id: str | None = None
        runtime_step_id: str | None = None
        runtime_provider: str | None = None
        current_agent = None

        # Resolve per-agent runtime provider override (hybrid / per_agent mode)
        agent_provider_override: str | None = None
        if workspace is not None:
            strategy = getattr(workspace, "execution_strategy", "fixed") or "fixed"
            if strategy in ("per_agent", "hybrid"):
                # Look up the calling agent for a per-agent runtime_provider
                for agent_handle in workspace.agents:
                    if agent_handle.agent_id == agent_id:
                        current_agent = agent_handle
                        agent_provider_override = getattr(agent_handle, "runtime_provider", None)
                        # Also check agent metadata
                        if agent_provider_override is None and isinstance(agent_handle.metadata, dict):
                            agent_provider_override = agent_handle.metadata.get("runtime_provider")
                        break
            if current_agent is None:
                current_agent = next(
                    (agent_handle for agent_handle in workspace.agents if agent_handle.agent_id == agent_id),
                    None,
                )

        ws_timeout = 90
        ws_recursion = 80
        if workspace and workspace.mode in {"branch", "group"}:
            ws_timeout = 360
        if workspace and workspace.metadata:
            if workspace.metadata.get("timeout_seconds"):
                ws_timeout = min(int(workspace.metadata["timeout_seconds"]), 7200)
            if workspace.metadata.get("max_turns"):
                ws_recursion = min(int(workspace.metadata["max_turns"]) * 2, 500)

        requires_tool_research = False
        subagent_enabled = False
        query_service = None
        if workspace is not None:
            from src.query_engine import get_query_engine_service

            query_service = get_query_engine_service()
            requires_tool_research = requires_tool_backed_research(workspace, request.content) or _prefers_server_side_news_fallback(
                workspace.goal or request.content
            )
            subagent_enabled = agent_supports_subagent_delegation(workspace, agent_id)
            query_session_id = resolve_query_session_id(
                workspace,
                agent_id,
                query_service=query_service,
            )
        if requires_tool_research:
            ws_recursion = min(ws_recursion, 96)
        if requires_tool_research and subagent_enabled:
            ws_recursion = min(ws_recursion, 120)
        runtime_provider = agent_provider_override or (workspace.agent_runtime_provider if workspace is not None else None)

        if query_session_id is not None:
            try:
                mark_query_session_running(
                    query_session_id,
                    query_service=query_service,
                    user_message=request.content,
                    created_at=utc_now(),
                )
            except Exception:
                logger.exception(
                    "Failed to mark query session %s as running for task %s agent %s",
                    query_session_id,
                    task_id,
                    agent_id,
                )

        get_agent_core_service().dispatch_execution_started(
            task_id,
            agent_id,
            query_session_id=query_session_id,
            runtime_provider=agent_provider_override,
        )

        tool_call_count = 0
        runtime_invocation_failed = False
        used_direct_fallback = False
        used_url_fetch_fallback = False
        used_server_side_fallback = False
        forced_failure_message = False
        fallback_query = workspace.goal if workspace is not None and workspace.goal else request.content

        fast_path_target = _server_side_fallback_target(fallback_query) if requires_tool_research else None
        if requires_tool_research and fast_path_target in {"server_side_ai_news_fallback", "server_side_news_fallback"}:
            assistant_content = build_server_side_research_fallback(fallback_query)
            if assistant_content:
                used_server_side_fallback = True
                tool_call_count = max(tool_call_count, 1)
            execution_target = execution_target or fast_path_target

        try:
            if assistant_content is None:
                primary_timeout = max(60, min(ws_timeout, 300))
                if requires_tool_research:
                    primary_timeout = max(primary_timeout, 180)
                if requires_tool_research and subagent_enabled:
                    primary_timeout = max(primary_timeout, min(ws_timeout, 240))
                invoke_kwargs = {
                    "model_override": request.model_override,
                    "timeout_seconds": primary_timeout,
                    "recursion_limit": ws_recursion,
                    "subagent_enabled": subagent_enabled,
                }
                if agent_provider_override:
                    invoke_kwargs["agent_runtime_provider_override"] = agent_provider_override
                if query_session_id is not None:
                    invoke_kwargs["query_session_id"] = query_session_id
                invoke_result = await invoke_agent_runtime(
                    task_id,
                    request.content,
                    workspace=workspace,
                    agent=current_agent,
                    **invoke_kwargs,
                )
                if isinstance(invoke_result, tuple) and len(invoke_result) >= 4:
                    assistant_content, tool_call_count, runtime_session_id, execution_target = invoke_result[:4]
                    if len(invoke_result) >= 5:
                        runtime_provider = invoke_result[4]
                    if len(invoke_result) >= 6 and isinstance(invoke_result[5], dict):
                        runtime_step_id = str(invoke_result[5].get("run_id") or "") or None
                else:
                    assistant_content, tool_call_count = invoke_result
        except Exception:
            runtime_invocation_failed = True
            logger.exception("Runtime invocation failed for task %s agent %s", task_id, agent_id)

        if requires_tool_research and tool_call_count == 0 and not runtime_invocation_failed:
            enforced_prompt = (
                "你必须先调用联网检索工具（例如 web_search/web_fetch）获取最新公开信息，再给结论。"
                "若无法联网或工具失败，必须明确写出失败原因与已尝试的工具，不可仅凭记忆作答。\n\n"
                f"原始任务：{request.content}"
            )
            try:
                retry_invoke_kwargs = {
                    "model_override": request.model_override,
                    "timeout_seconds": max(90, min(ws_timeout, 180)),
                    "recursion_limit": ws_recursion,
                    "subagent_enabled": subagent_enabled,
                }
                if agent_provider_override:
                    retry_invoke_kwargs["agent_runtime_provider_override"] = agent_provider_override
                if query_session_id is not None:
                    retry_invoke_kwargs["query_session_id"] = query_session_id
                retry_result = await invoke_agent_runtime(
                    task_id,
                    enforced_prompt,
                    workspace=workspace,
                    agent=current_agent,
                    **retry_invoke_kwargs,
                )
                if isinstance(retry_result, tuple) and len(retry_result) >= 4:
                    retry_content, retry_tool_calls, retry_runtime_session_id, retry_execution_target = retry_result[:4]
                    runtime_session_id = retry_runtime_session_id or runtime_session_id
                    execution_target = retry_execution_target or execution_target
                    if len(retry_result) >= 5 and retry_result[4]:
                        runtime_provider = retry_result[4]
                    if len(retry_result) >= 6 and isinstance(retry_result[5], dict):
                        runtime_step_id = str(retry_result[5].get("run_id") or "") or runtime_step_id
                else:
                    retry_content, retry_tool_calls = retry_result
                if retry_content:
                    assistant_content = retry_content
                tool_call_count = max(tool_call_count, retry_tool_calls)
            except Exception:
                logger.exception("Runtime enforcement retry failed for task %s agent %s", task_id, agent_id)

        if requires_tool_research and not used_server_side_fallback:
            should_force_server_fallback = (
                assistant_content is None
                or tool_call_count == 0
                or output_indicates_hard_failure(assistant_content)
            )
            if should_force_server_fallback:
                assistant_content = build_server_side_research_fallback(fallback_query)
                if assistant_content:
                    used_server_side_fallback = True
                    tool_call_count = max(tool_call_count, 1)
                    execution_target = execution_target or _server_side_fallback_target(fallback_query)

        allow_direct_fallback = not requires_tool_research and not subagent_enabled
        if assistant_content is None and allow_direct_fallback:
            assistant_content = await run_direct_model_fallback(
                request=request,
                task_id=task_id,
                agent_id=agent_id,
                ws_timeout=ws_timeout,
            )
            used_direct_fallback = assistant_content is not None

        if assistant_content is None and requires_tool_research:
            assistant_content = (
                "Execution failed: research workflow did not produce a valid tool-backed answer. "
                "No reliable web/tool evidence was captured, so direct memory-only output was rejected."
            )
            forced_failure_message = True
        if assistant_content is None and subagent_enabled:
            assistant_content = (
                "Execution failed: multi-agent workflow did not return a valid LangGraph result. "
                "Direct single-model fallback is disabled for group/branch mode to avoid bypassing tools and coordination."
            )
            forced_failure_message = True
        if workspace is not None and requires_tool_research and tool_call_count == 0 and not used_server_side_fallback:
            assistant_content = (
                f"{assistant_content}\n\n"
                "Validation note: expected at least one web/tool call for this research task, "
                "but none were observed in LangGraph traces."
            )

        if query_session_id is not None:
            execution_status = "blocked"
            if assistant_content is not None and not forced_failure_message:
                execution_status = (
                    "simulated"
                    if used_direct_fallback or used_url_fetch_fallback or used_server_side_fallback or runtime_invocation_failed
                    else "completed"
                )
            try:
                record_query_agent_execution(
                    query_session_id,
                    query_service=query_service,
                    user_message=request.content,
                    assistant_summary=assistant_content or "",
                    tool_call_count=tool_call_count,
                    execution_target=execution_target,
                    execution_status=execution_status,
                    runtime_provider=runtime_provider,
                    runtime_session_id=runtime_session_id,
                    runtime_step_id=runtime_step_id,
                    created_at=utc_now(),
                )
            except Exception:
                logger.exception(
                    "Failed to record query-engine execution for task %s agent %s",
                    task_id,
                    agent_id,
                )
        result = append_message(task_id, agent_id, request, assistant_content=assistant_content)

        get_agent_core_service().dispatch_execution_finished(
            task_id,
            agent_id,
            tool_call_count=tool_call_count,
            runtime_provider=runtime_provider,
            execution_target=execution_target,
            used_direct_fallback=used_direct_fallback,
            used_url_fetch_fallback=used_url_fetch_fallback,
            used_server_side_fallback=used_server_side_fallback,
            forced_failure_message=forced_failure_message,
            runtime_invocation_failed=runtime_invocation_failed,
            query_session_id=query_session_id,
            runtime_session_id=runtime_session_id,
        )

        return result


_execution_controller = TaskWorkspaceExecutionController()
_message_executor = TaskWorkspaceMessageExecutor()


def get_task_workspace_execution_controller() -> TaskWorkspaceExecutionController:
    return _execution_controller


def get_task_workspace_message_executor() -> TaskWorkspaceMessageExecutor:
    return _message_executor
