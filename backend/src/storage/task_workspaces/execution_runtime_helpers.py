from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from src.agents.core.prompts import (
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
    del timeout_seconds

    response = await send_message(
        task_id,
        agent.agent_id,
        CreateAgentMessageRequest(content=prompt, model_override=agent.model_name),
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
    current_prompt = initial_prompt
    new_transcripts: list[str] = []

    try:
        return await execute_agent_step(
            workspace.task_id,
            worker_agent,
            current_prompt,
            send_message,
            timeout_seconds,
        )
    except TimeoutError:
        logger.warning(
            "Worker %s reported a provider timeout for task %s; converting to soft handoff",
            worker_agent.name,
            workspace.task_id,
        )
        new_transcripts.append(f"**[软交接] {worker_agent.name}** 底层 provider 返回 timeout 信号；系统不把该段标记为硬失败，改由主代理基于现有上下文继续汇总。")
        analysis_prompt = build_worker_timeout_analysis_prompt(
            goal=goal,
            agent_name=worker_agent.name,
            agent_task_scope=worker_agent.task_scope or worker_agent.role,
            timeout_seconds=timeout_seconds,
            timeout_count=1,
            coordinator_output=coordinator_output,
            prior_worker_outputs=prior_worker_outputs,
        )
        takeover_prompt = build_worker_takeover_prompt(
            goal=goal,
            agent_name=worker_agent.name,
            agent_task_scope=worker_agent.task_scope or worker_agent.role,
            timeout_seconds=timeout_seconds,
            coordinator_output=coordinator_output,
            prior_worker_outputs=prior_worker_outputs,
            timeout_analyses=[analysis_prompt],
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
            new_transcripts.append(f"**[软交接完成] {lead_agent.name} 已接管 {worker_agent.name} 的任务段。")
            return takeover_output, new_transcripts
        except TimeoutError:
            advisory = f"{worker_agent.name} 的任务段暂未返回完整结果。请在最终汇总中明确列出该段的已知上下文、缺口和下一步验证方式；这不是系统硬失败。"
            new_transcripts.append("**[软交接保留]** 主代理接管也收到 timeout 信号，保留为可见诊断。")
            return advisory, new_transcripts


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
        del ws_timeout
        ai_msg = await asyncio.to_thread(model.invoke, [HumanMessage(content=request.content)])
        if not ai_msg or not ai_msg.content:
            return None
        content = ai_msg.content
        if isinstance(content, list):
            text_parts = [part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"]
            content = "\n".join(text_parts)
        return str(content or "").strip() or None
    except Exception:
        logger.exception("Direct model fallback also failed for task %s agent %s", task_id, agent_id)
        return None
