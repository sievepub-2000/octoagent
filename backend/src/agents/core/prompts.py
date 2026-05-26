"""Agent execution prompt templates (Slice F extraction).

Pure functions that produce structured prompts for lead, worker,
reviewer, and synthesis agent steps.  No heavy runtime dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.agents.core.instruction_contracts import build_contract_prompt, detect_instruction_contract

if TYPE_CHECKING:
    from src.storage.task_workspaces.contracts import AgentHandle, AgentMessage, TaskWorkspace


# ------------------------------------------------------------------
# Transcript formatting
# ------------------------------------------------------------------


def _instruction_contract_block(goal: str, metadata: dict | None = None) -> str:
    contract = detect_instruction_contract(goal, metadata=metadata)
    rendered = build_contract_prompt(contract)
    return f"{rendered}\n\n"


def format_transcript_messages(
    agent: AgentHandle,
    messages: list[AgentMessage],
) -> tuple[str, list[str]]:
    """Extract the last assistant output and build transcript lines."""
    assistant_output = ""
    transcript_lines: list[str] = []
    tail_messages = messages[-3:] if len(messages) > 3 else messages
    for message in tail_messages:
        content = str(message.content or "").strip()
        if not content:
            continue
        transcript_lines.append(f"**{agent.name} · {message.role}**: {content[:600]}")
        if message.role == "assistant":
            assistant_output = content
    return assistant_output, transcript_lines


# ------------------------------------------------------------------
# Lead agent prompts
# ------------------------------------------------------------------


def build_lead_agent_prompt(
    workspace: TaskWorkspace,
    goal: str,
    attempt: int,
    last_output: str,
    last_failure_reason: str | None,
    sub_agent_names: list[str],
) -> str:
    """Build the prompt for the lead agent at a given attempt."""
    has_sub_agents = len(sub_agent_names) > 0
    sub_desc = "、".join(sub_agent_names) if has_sub_agents else "（无子agent，请自主执行）"
    is_multi_agent = workspace.mode in {"group", "branch"} and has_sub_agents
    contract_block = _instruction_contract_block(goal, workspace.metadata)
    if attempt == 1:
        if is_multi_agent:
            return (
                contract_block + f"你是主代理（协调者），必须通过以下专项子agents完成任务：{sub_desc}。\n\n"
                "## 执行规则\n"
                "1. 不允许绕过子agents直接把任务当作单链任务完成。\n"
                "2. 必须先给出分工，再基于子agent的真实输出做汇总。\n"
                "3. 若子agent输出不足，必须指出缺口并继续督导，而不是伪造完成。\n\n"
                "## 输出要求\n"
                "最终输出必须：完整、可验证，并明确引用子agent的实际结果。\n\n"
                f"任务目标：{goal}"
            )
        return (
            contract_block + "你是负责执行以下任务的智能体。\n\n"
            "执行规则：\n"
            "1. 调用必要的工具完成任务（web_search、web_fetch、read_webpage等）；\n"
            "2. 完成后输出完整的、可验证的结果；\n"
            "3. 结果中如使用了联网或工具信息，必须标明来源。\n\n"
            f"任务目标：{goal}"
        )

    prev_summary = (last_output[:800] + "…") if len(last_output) > 800 else last_output
    retry_header = (
        f"## 第 {attempt} 次重试执行\n\n"
        f"前 {attempt - 1} 次执行未达到预期结果。\n"
        f"失败/不足原因：{last_failure_reason or '输出不符合预期要求'}\n\n"
        f"上一轮输出摘要：\n{prev_summary}\n\n"
        "---\n\n"
        "请你（主代理）根据以上信息，分析失败原因，优化执行方案，"
    )
    if is_multi_agent:
        return contract_block + retry_header + f"然后重新分配并督导子agents（{sub_desc}）完成任务。\n注意：你不能跳过子agent直接得出结论；最终结果必须基于子agent真实输出。\n\n原始任务目标：{goal}"
    return contract_block + retry_header + "然后重新执行任务，确保结果完整可验证。\n\n" + f"原始任务目标：{goal}"


# ------------------------------------------------------------------
# Multi-agent coordination prompts
# ------------------------------------------------------------------


def build_multi_agent_kickoff_prompt(
    workspace: TaskWorkspace,
    goal: str,
    worker_agents: list[AgentHandle],
    review_agent: AgentHandle | None,
    attempt: int,
    last_output: str,
    last_failure_reason: str | None,
) -> str:
    """Build the kickoff prompt for the lead agent in multi-agent mode."""
    worker_desc = "、".join(f"{agent.name}（{agent.task_scope}）" for agent in worker_agents) or "无"
    review_desc = review_agent.name if review_agent is not None else "无"
    retry_context = ""
    if attempt > 1:
        prev_summary = (last_output[:800] + "…") if len(last_output) > 800 else last_output
        retry_context = f"\n## 纠错上下文\n- 上一轮失败原因：{last_failure_reason or '结果不完整'}\n- 上一轮结果摘要：{prev_summary or '（无）'}\n"
    return (
        _instruction_contract_block(goal, workspace.metadata) + f"你是 {workspace.mode} 工作流的主协调代理，负责制定分工计划并最终汇总各子代理的输出。\n\n"
        f"任务目标：{goal}\n\n"
        f"执行成员：\n- Worker：{worker_desc}\n- Reviewer：{review_desc}\n"
        f"要求：\n"
        f"1. 给出明确分工和验收标准（系统会自动将任务分配给对应 worker，你无需手动调用工具委派）。\n"
        f"2. 后续汇总阶段必须基于各子代理产出进行综合分析。\n"
        f"3. 若信息不足，明确指出缺口，不可伪造已完成验证。\n"
        f"4. 最终收口时必须引用各子代理的真实输出。"
        f"{retry_context}"
    )


def build_worker_prompt(
    goal: str,
    coordinator_output: str,
    agent: AgentHandle,
    shared_outputs: dict[str, str],
) -> str:
    """Build the task prompt for a worker agent."""
    prior_outputs = "\n\n".join(f"[{name}]\n{output}" for name, output in shared_outputs.items() if output.strip()) or "（暂无其他 worker 输出）"
    return (
        _instruction_contract_block(goal) + f"你是 {agent.name}，职责是：{agent.task_scope or agent.role}。\n\n"
        f"总任务：{goal}\n\n"
        f"协调者要求：\n{coordinator_output or '（协调者未提供额外说明，请直接围绕目标执行）'}\n\n"
        f"其他已完成 worker 输出：\n{prior_outputs}\n\n"
        f"请只完成你职责范围内的工作，输出可验证结果、实际观察、失败项和证据。"
    )


def build_reviewer_prompt(goal: str, worker_outputs: dict[str, str]) -> str:
    """Build the review prompt for the reviewer agent."""
    combined = "\n\n".join(f"[{name}]\n{output}" for name, output in worker_outputs.items()) or "（无 worker 输出）"
    return _instruction_contract_block(goal) + f"你是 Review Agent，负责核查以下任务是否真正完成：{goal}\n\n待核查 worker 输出：\n{combined}\n\n请输出：完成项、缺失项、可疑结论、是否可以交付。若不能交付，必须明确拒绝。"


def build_worker_timeout_analysis_prompt(
    goal: str,
    agent_name: str,
    agent_task_scope: str,
    timeout_seconds: int,
    timeout_count: int,
    coordinator_output: str,
    prior_worker_outputs: dict[str, str],
) -> str:
    """Prompt for lead agent to analyze worker timeout and produce a new execution plan."""
    prior_block = "\n\n".join(f"[{name}]\n{output}" for name, output in prior_worker_outputs.items() if output.strip()) or "（暂无其他 worker 输出）"
    return (
        _instruction_contract_block(goal) + f"子代理 **{agent_name}**（职责：{agent_task_scope}）在执行过程中超时（超过 {timeout_seconds}s 未返回）。\n"
        f"这是第 {timeout_count} 次超时。\n\n"
        f"总任务目标：{goal}\n\n"
        f"你之前的协调计划：\n{coordinator_output or '（无）'}\n\n"
        f"已完成的其他 worker 输出：\n{prior_block}\n\n"
        f"请分析该 worker 超时的可能原因（任务太复杂/范围太宽/依赖外部资源/描述不清等），"
        f"然后给出一个更精简、更具体、更易于在 {timeout_seconds}s 内完成的优化执行方案，"
        f"直接输出给 {agent_name} 的新任务指令（不超过 400 字），确保新方案可以在时限内完成。"
    )


def build_worker_takeover_prompt(
    goal: str,
    agent_name: str,
    agent_task_scope: str,
    timeout_seconds: int,
    coordinator_output: str,
    prior_worker_outputs: dict[str, str],
    timeout_analyses: list[str],
) -> str:
    """Prompt for lead agent to directly execute the failed worker's task after 3 timeouts."""
    prior_block = "\n\n".join(f"[{name}]\n{output}" for name, output in prior_worker_outputs.items() if output.strip()) or "（暂无）"
    analyses_block = "\n\n".join(f"第{i + 1}次超时分析：{a}" for i, a in enumerate(timeout_analyses))
    return (
        _instruction_contract_block(goal) + f"子代理 **{agent_name}**（职责：{agent_task_scope}）已连续 3 次超时，无法继续由其执行。\n\n"
        f"总任务目标：{goal}\n\n"
        f"三次超时分析摘要：\n{analyses_block}\n\n"
        f"已完成的其他 worker 输出：\n{prior_block}\n\n"
        f"你（主协调代理）现在需要**亲自完成**原本属于 {agent_name} 的工作（{agent_task_scope}）。\n"
        f"请在 {timeout_seconds}s 内尽最大努力完成，输出可验证的实际结果。\n"
        f"不可以简单说\u300c无法完成\u300d\u2014\u2014请真实尝试后给出结果，哪怕部分完成也要写清楚完成了哪些、阻塞在哪里。"
    )


def build_final_synthesis_prompt(
    goal: str,
    coordinator_output: str,
    worker_outputs: dict[str, str],
    review_output: str,
) -> str:
    """Build the final synthesis prompt for the lead agent."""
    workers_block = "\n\n".join(f"[{name}]\n{output}" for name, output in worker_outputs.items()) or "（无 worker 输出）"
    return (
        _instruction_contract_block(goal) + f"请基于真实执行记录给出最终结果。\n\n"
        f"任务目标：{goal}\n\n"
        f"协调计划：\n{coordinator_output or '（无）'}\n\n"
        f"Worker 输出：\n{workers_block}\n\n"
        f"Review 结论：\n{review_output or '（无 reviewer 输出）'}\n\n"
        f"要求：\n"
        f"1. 只能引用上述真实输出。\n"
        f"2. 如果 worker 或 reviewer 没有完成，就明确写失败或阻塞。\n"
        f"3. 不可把 fallback、空输出或猜测写成完成。"
    )


__all__ = [
    "build_final_synthesis_prompt",
    "build_lead_agent_prompt",
    "build_lead_direct_execution_prompt",
    "build_lead_optimization_plan_prompt",
    "build_multi_agent_kickoff_prompt",
    "build_reviewer_prompt",
    "build_worker_prompt",
    "build_worker_self_analysis_prompt",
    "build_worker_stage2_prompt",
    "build_worker_takeover_prompt",
    "build_worker_timeout_analysis_prompt",
    "format_transcript_messages",
]


# ------------------------------------------------------------------
# 3-3-6 escalation prompts
# ------------------------------------------------------------------


def _format_failure_history(history: list[dict]) -> str:
    """Render a compact, readable list of prior failed attempts.

    ``history`` items are dicts with ``attempt``, ``reason`` (str) and
    optional ``output`` preview (str).
    """
    if not history:
        return "（无）"
    lines: list[str] = []
    for item in history:
        attempt_no = item.get("attempt", "?")
        reason = str(item.get("reason") or "").strip() or "未记录原因"
        output_preview = str(item.get("output") or "").strip()
        if len(output_preview) > 280:
            output_preview = output_preview[:280] + "…"
        lines.append(f"- 第 {attempt_no} 次失败：{reason}" + (f"\n  输出摘要：{output_preview}" if output_preview else ""))
    return "\n".join(lines)


def build_worker_self_analysis_prompt(
    goal: str,
    prior_failures: list[dict],
    attempt_index: int,
    agent_name: str | None = None,
) -> str:
    """Stage 1 (attempts 2-3): worker reflects on its own prior failures.

    The sub-agent analyzes why previous attempts failed, proposes concrete
    adjustments (tool choice, query phrasing, sub-steps), and retries.
    """
    who = f"你（{agent_name}）" if agent_name else "你"
    history_block = _format_failure_history(prior_failures)
    return (
        _instruction_contract_block(goal) + f"## 子代理自我复盘（第 {attempt_index} 次尝试 / 阶段一）\n\n"
        f"任务目标：{goal}\n\n"
        f"{who}在前几次尝试中未能完成任务。历史如下：\n{history_block}\n\n"
        "请按以下步骤重新执行：\n"
        "1. 用 2-3 句话写出本次对上面失败原因的分析（工具用错？查询过宽？缺少数据源？）。\n"
        "2. 列出这一轮会采取的具体优化动作（例如换用更准确的 web_search 关键词、改用 direct URL fetch、拆分子查询）。\n"
        "3. 实际调用工具执行并给出可验证的完整结果，标注信息来源。\n\n"
        "要求：必须真正调用工具（web_search / web_fetch / read_webpage / direct URL fetch 等），"
        "不可只是复述上一轮的失败结论。"
    )


def build_lead_optimization_plan_prompt(
    goal: str,
    stage1_failures: list[dict],
    sub_agent_name: str | None = None,
) -> str:
    """Stage 2 entry: lead agent analyzes 3 stage-1 failures and produces a plan.

    The lead reviews the sub-agent's three failed attempts and emits a
    concrete, step-by-step execution plan that will be injected into the
    sub-agent prompts for attempts 4-6.
    """
    target = sub_agent_name or "子代理"
    history_block = _format_failure_history(stage1_failures)
    return (
        _instruction_contract_block(goal) + "## 主代理升级介入（阶段二开始）\n\n"
        f"任务目标：{goal}\n\n"
        f"{target} 已经自我重试 3 次仍然失败，下面是三次失败的完整记录：\n\n"
        f"{history_block}\n\n"
        "作为主协调代理，请你完成下面的工作并直接输出结果（不要执行任务本身，只输出计划）：\n\n"
        "1. **根因分析**：归纳这三次失败共同的根本原因（2-4 条要点）。\n"
        "2. **优化执行方案**：给出一份可以直接交给子代理的、分步骤的新执行计划，要求：\n"
        "   - 每一步说明用什么工具、参数/关键词建议、预期产出。\n"
        "   - 如果需要更换数据源或换一种拆解方式，请明确说出。\n"
        "   - 计划要具体、可验证，不要泛泛而谈。\n"
        "3. **验收标准**：列出子代理本次必须输出哪些字段/结构才算通过。\n\n"
        "你的输出将被直接用作接下来 3 次子代理重试的执行指令。"
    )


def build_worker_stage2_prompt(
    goal: str,
    optimization_plan: str,
    attempt_index: int,
    stage1_failures: list[dict],
    stage2_failures: list[dict],
    agent_name: str | None = None,
) -> str:
    """Stage 2 (attempts 4-6): worker executes the lead-provided optimization plan."""
    who = f"你（{agent_name}）" if agent_name else "你"
    plan_text = optimization_plan.strip() or "（主代理未给出有效计划，请自行按目标最佳方式执行）"
    history_block = _format_failure_history(stage1_failures + stage2_failures)
    return (
        _instruction_contract_block(goal) + f"## 阶段二：按主代理优化方案执行（第 {attempt_index} 次尝试）\n\n"
        f"任务目标：{goal}\n\n"
        "主代理针对此前失败给出的优化执行方案如下：\n"
        "-----\n"
        f"{plan_text}\n"
        "-----\n\n"
        f"之前全部失败记录（仅供参考）：\n{history_block}\n\n"
        f"请{who}严格按照上述方案执行，务必真正调用工具、真正产生可验证结果。"
        "最后标注信息来源。"
    )


def build_lead_direct_execution_prompt(
    goal: str,
    all_failures: list[dict],
) -> str:
    """Stage 3 (attempt 7): lead takes over and executes the task directly.

    After 6 sub-agent failures (3 self-analysis + 3 lead-optimized), the
    lead agent must now analyze *all* 6 failures and personally carry out
    the task.
    """
    history_block = _format_failure_history(all_failures)
    return (
        _instruction_contract_block(goal) + "## 主代理亲自执行（阶段三 · 最终介入）\n\n"
        f"任务目标：{goal}\n\n"
        f"子代理在两个阶段共 6 次尝试全部失败，完整记录如下：\n\n"
        f"{history_block}\n\n"
        "现在作为主代理，请完成下面的工作并**直接产出最终结果**：\n\n"
        "1. **六次失败复盘**：用要点形式总结 6 次失败中最关键的 2-3 个问题。\n"
        "2. **最新优化方案**：写出本次你自己将采用的执行策略（可以和之前给子代理的方案不同，"
        "强调你将如何绕开之前卡住的点）。\n"
        "3. **亲自执行**：立即调用必要工具（web_search / web_fetch / read_webpage 等），"
        "真实完成任务并输出完整、可验证的结果，标注来源。\n\n"
        "要求：本轮不能再把任务分派给子代理；你必须亲自完成或明确写出仍然阻塞的具体原因。"
    )
