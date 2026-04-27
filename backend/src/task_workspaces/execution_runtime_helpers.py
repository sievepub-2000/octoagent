from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from src.agent_core.prompts import (
    build_worker_prompt,
    build_worker_takeover_prompt,
    build_worker_timeout_analysis_prompt,
    format_transcript_messages,
)

from .contracts import AgentHandle, CreateAgentMessageRequest

logger = logging.getLogger(__name__)


async def execute_agent_step(
    task_id: str,
    agent: AgentHandle,
    prompt: str,
    send_message: Callable[[str, str, CreateAgentMessageRequest], Awaitable[object]],
    timeout_seconds: int,
) -> tuple[str, list[str]]:
    import asyncio

    response = await asyncio.wait_for(
        send_message(
            task_id,
            agent.agent_id,
            CreateAgentMessageRequest(content=prompt, model_override=agent.model_name),
        ),
        timeout=timeout_seconds,
    )
    assistant_output, transcript_lines = format_transcript_messages(agent, response.messages)
    return assistant_output, transcript_lines


async def execute_worker_with_timeout_recovery(
    *,
    workspace,
    goal: str,
    worker_agent,
    initial_prompt: str,
    coordinator_output: str,
    prior_worker_outputs: dict[str, str],
    send_message,
    lead_agent,
    timeout_seconds: int,
) -> tuple[str, list[str]]:
    max_worker_retries = 2
    timeout_analyses: list[str] = []
    current_prompt = initial_prompt
    new_transcripts: list[str] = []

    for attempt_num in range(1, max_worker_retries + 2):
        try:
            return await execute_agent_step(
                workspace.task_id,
                worker_agent,
                current_prompt,
                send_message,
                timeout_seconds,
            )
        except TimeoutError:
            timeout_count = attempt_num
            logger.warning(
                "Worker %s timed out (attempt %d/%d) for task %s",
                worker_agent.name,
                timeout_count,
                max_worker_retries + 1,
                workspace.task_id,
            )
            new_transcripts.append(
                f"**[超时] {worker_agent.name}** 第 {timeout_count} 次超时（>{timeout_seconds}s）"
            )

            if attempt_num <= max_worker_retries:
                analysis_prompt = build_worker_timeout_analysis_prompt(
                    goal=goal,
                    agent_name=worker_agent.name,
                    agent_task_scope=worker_agent.task_scope or worker_agent.role,
                    timeout_seconds=timeout_seconds,
                    timeout_count=timeout_count,
                    coordinator_output=coordinator_output,
                    prior_worker_outputs=prior_worker_outputs,
                )
                try:
                    analysis_output, analysis_transcript = await execute_agent_step(
                        workspace.task_id,
                        lead_agent,
                        analysis_prompt,
                        send_message,
                        timeout_seconds,
                    )
                except TimeoutError:
                    analysis_output = f"（主代理分析第{timeout_count}次超时时也超时，使用原始计划重试）"
                    analysis_transcript = []

                timeout_analyses.append(analysis_output)
                new_transcripts.append(
                    f"**[主代理超时分析 {timeout_count}]** {worker_agent.name}：\n{analysis_output[:600]}"
                )
                new_transcripts.extend(analysis_transcript)
                current_prompt = build_worker_prompt(
                    goal,
                    analysis_output,
                    worker_agent,
                    prior_worker_outputs,
                )
                continue

            new_transcripts.append(
                f"**[接管] {worker_agent.name} 连续 3 次超时，主代理 {lead_agent.name} 亲自执行**"
            )
            takeover_prompt = build_worker_takeover_prompt(
                goal=goal,
                agent_name=worker_agent.name,
                agent_task_scope=worker_agent.task_scope or worker_agent.role,
                timeout_seconds=timeout_seconds,
                coordinator_output=coordinator_output,
                prior_worker_outputs=prior_worker_outputs,
                timeout_analyses=timeout_analyses,
            )
            try:
                takeover_output, takeover_transcript = await execute_agent_step(
                    workspace.task_id,
                    lead_agent,
                    takeover_prompt,
                    send_message,
                    timeout_seconds,
                )
                new_transcripts.extend(takeover_transcript)
                new_transcripts.append(
                    f"**[接管完成] {lead_agent.name} 代替 {worker_agent.name} 执行完毕**"
                )
                return takeover_output, new_transcripts
            except TimeoutError:
                failure_marker = (
                    f"[worker_timeout_failure] {worker_agent.name} 连续超时且主代理接管也超时，"
                    f"任务段 '{worker_agent.task_scope or worker_agent.role}' 无法完成。"
                )
                new_transcripts.append(f"**[接管超时] {lead_agent.name} 接管也超时，标记失败**")
                return failure_marker, new_transcripts

    return f"[worker_timeout_failure] {worker_agent.name} 超时且恢复失败", new_transcripts


async def run_direct_model_fallback(
    *,
    request: CreateAgentMessageRequest,
    task_id: str,
    agent_id: str,
    ws_timeout: int,
) -> str | None:
    import asyncio

    from langchain_core.messages import HumanMessage

    from src.models import create_chat_model

    try:
        model = create_chat_model(name=request.model_override or None, thinking_enabled=False)
        ai_msg = await asyncio.wait_for(
            asyncio.to_thread(model.invoke, [HumanMessage(content=request.content)]),
            timeout=max(20, min(ws_timeout, 60)),
        )
        if not ai_msg or not ai_msg.content:
            return None
        content = ai_msg.content
        if isinstance(content, list):
            text_parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            content = "\n".join(text_parts)
        return str(content or "").strip() or None
    except Exception:
        logger.exception("Direct model fallback also failed for task %s agent %s", task_id, agent_id)
        return None