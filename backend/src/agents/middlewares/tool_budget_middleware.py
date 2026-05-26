"""Recover failed tool calls and stop only truly exhausted tool loops."""

from __future__ import annotations

import hashlib
import json
import logging
import os as _os
import re
import threading
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command

from src.utils.messages import latest_human_index as _latest_human_index
from src.utils.messages import message_text as _message_text

logger = logging.getLogger(__name__)

_DUPLICATE_TOOL_CALL_LIMIT = int(_os.environ.get("OCTO_TOOL_DUPLICATE_LIMIT", "4"))
_DUPLICATE_TOOL_CALL_HARD_LIMIT = int(_os.environ.get("OCTO_TOOL_DUPLICATE_HARD_LIMIT", "8"))
_TOOL_LOOP_HARD_STOP_KEY = "octo_tool_loop_hard_stop"
_PLANNING_LOOP_FINALIZE_DUP = int(_os.environ.get("OCTO_PLANNING_LOOP_FINALIZE_DUP", "8"))
_SELF_CONSTRAINT_MARKER = "<runtime_self_constraint_reflection>"

# 2026-05-16: Disable memory-derived soft budgets by default to prevent
# premature task termination. Set OCTO_TOOL_SOFT_BUDGET_FROM_MEMORY=1 to re-enable.
_SOFT_BUDGET_FROM_MEMORY_ENABLED = _os.environ.get("OCTO_TOOL_SOFT_BUDGET_FROM_MEMORY", "0").strip().lower() in ("1", "true", "yes", "on")

_AUTO_DESCRIPTION_TOOLS = {"bash", "ls", "read_file", "write_file", "str_replace"}
_RECOVERY_GUARD_KEY = "octo_tool_recovery_guard"
_PLANNING_NOOP_GUARD_KEY = "octo_planning_noop_guard"
_CORE_DISCOVERY_TOOLS = {
    "list_capabilities",
    "load_skill",
    "get_plugin_command",
    "read_webpage",
}
_OPENHARNESS_DISCOVERY_TOOLS = {"web_search", "web_fetch"}
_ERROR_PREFIXES = (
    "error:",
    "error invoking tool",
    "error executing tool",
    "http error",
    "tool failed",
    "failed:",
    "traceback",
)
_ERROR_MARKERS = (
    "field required",
    "validationerror",
    "please fix the error",
    "not a valid tool",
    "is not registered",
    "timed out",
    "connectionerror",
    "permission denied",
    "file not found",
    "directory not found",
)
_WEB_RESEARCH_TOOLS = {"web_search", "web_fetch", "web_fetch_heavy", "read_webpage", "scrapling_fetch"}
_RESEARCH_CLOSURE_GUARD_KEY = "octo_research_closure_guard"
_RESEARCH_EVIDENCE_COMPACTED_KEY = "octo_research_evidence_compacted"
_RESEARCH_CLOSURE_TOOL_LIMIT = int(_os.environ.get("OCTO_RESEARCH_CLOSURE_TOOL_LIMIT", "6"))
_RESEARCH_CLOSURE_FETCH_LIMIT = int(_os.environ.get("OCTO_RESEARCH_CLOSURE_FETCH_LIMIT", "4"))
_RESEARCH_CLOSURE_MIN_SUBSTANTIVE = int(_os.environ.get("OCTO_RESEARCH_CLOSURE_MIN_SUBSTANTIVE", "4"))
_RESEARCH_CLOSURE_SELF_REFLECT_EXTRA_TOOLS = int(_os.environ.get("OCTO_RESEARCH_CLOSURE_SELF_REFLECT_EXTRA_TOOLS", "2"))
_RESEARCH_CLOSURE_BLOCK_WEB_TOOLS = _os.environ.get("OCTO_RESEARCH_CLOSURE_BLOCK_WEB_TOOLS", "0").strip().lower() in {"1", "true", "yes", "on"}
_TOOL_RECOVERY_LEGACY_BLOCK_FINAL_TOOLS_REQUESTED = _os.environ.get("OCTO_TOOL_RECOVERY_BLOCK_FINAL_TOOLS", "0").strip().lower() in {"1", "true", "yes", "on"}
_RESEARCH_SUBSTANTIVE_CHARS = int(_os.environ.get("OCTO_RESEARCH_SUBSTANTIVE_CHARS", "240"))
_RESEARCH_COMPACT_CHARS = int(_os.environ.get("OCTO_RESEARCH_COMPACT_CHARS", "1200"))


@dataclass(frozen=True)
class ToolErrorEntry:
    tool_name: str
    content: str
    signature: str


_SOFT_BUDGET_MEMORY_TTL_SECONDS = 60.0
_soft_budget_cache_lock = threading.Lock()
_soft_budget_cache: tuple[float, int | None] = (0.0, None)
_RECOVERY_LESSON_CACHE_MAX = 512
_recovery_lesson_cache_lock = threading.Lock()
_recovery_lesson_hashes: set[str] = set()

_SOFT_BUDGET_PATTERNS = (
    re.compile(r"(?i)max[_\s-]?tool[_\s-]?(?:messages|calls)\s*[:=]\s*(\d{1,6})"),
    re.compile(r"(?i)tool[_\s-]?(?:call[_\s-]?)?(?:soft[_\s-]?)?(?:budget|limit)\D{0,40}(\d{1,6})"),
    re.compile(r"工具(?:调用)?(?:软上限|软预算|预算|上限)\D{0,40}(\d{1,6})"),
)




def _tool_message_is_error(message: ToolMessage) -> bool:
    if getattr(message, "status", None) == "error":
        return True
    text = _message_text(message).strip().lower()
    if not text:
        return False
    return text.startswith(_ERROR_PREFIXES) or any(marker in text for marker in _ERROR_MARKERS)


def _openharness_discovery_enabled() -> bool:
    return _os.environ.get("OCTOAGENT_OPENHARNESS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _discovery_tools() -> set[str]:
    tools = set(_CORE_DISCOVERY_TOOLS)
    if _openharness_discovery_enabled():
        tools.update(_OPENHARNESS_DISCOVERY_TOOLS)
    return tools


def _discovery_tool_names() -> str:
    return ", ".join(sorted(_discovery_tools()))


def _discovery_guidance_en() -> str:
    return "use " + _discovery_tool_names() + " to find an alternative"


def _discovery_guidance_zh() -> str:
    return "调用 " + _discovery_tool_names() + " 来寻找替代能力"


def _is_recovery_guard_message(message: ToolMessage) -> bool:
    if getattr(message, "additional_kwargs", {}).get(_RECOVERY_GUARD_KEY):
        return True
    text = _message_text(message)
    return (
        "Recovery policy requires" in text
        or text.startswith("工具调用连续失败，已按恢复策略停止继续消耗工具调用。")
        or text.startswith("Error: this exact tool call")
    )


def _is_write_todos_duplicate_guard(message: ToolMessage) -> bool:
    return str(getattr(message, "name", "") or "") == "write_todos" and _message_text(message).startswith(
        "Error: this exact tool call (write_todos"
    )


def _is_planning_noop_guard(message: ToolMessage) -> bool:
    return str(getattr(message, "name", "") or "") == "write_todos" and bool(
        getattr(message, "additional_kwargs", {}).get(_PLANNING_NOOP_GUARD_KEY)
    )


def _recovery_guard_message(*, content: str, name: str, tool_call_id: str | None) -> ToolMessage:
    return ToolMessage(
        content=content,
        name=name,
        tool_call_id=tool_call_id,
        status="error",
        additional_kwargs={_RECOVERY_GUARD_KEY: True},
    )


def _planning_noop_guard_message(*, dup_count: int, tool_call_id: str | None) -> ToolMessage:
    return ToolMessage(
        content=(
            f"Todo planning update skipped: the same write_todos call has already been attempted {dup_count} times in this turn. "
            "Treat the current todo state as sufficient. Prefer not to call write_todos again this turn; continue the user's task by "
            "using evidence-gathering tools such as web_search/web_fetch/read_webpage, or produce the final report if evidence is sufficient."
        ),
        name="write_todos",
        tool_call_id=tool_call_id,
        status="success",
        additional_kwargs={_PLANNING_NOOP_GUARD_KEY: True},
    )


def _json_tool_payload_is_error(text: str) -> bool:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return False
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("error"):
        return True
    if payload.get("ok") is False:
        return True
    for key in ("exit_code", "returncode"):
        value = payload.get(key)
        if value is None:
            continue
        try:
            if int(value) != 0:
                return True
        except (TypeError, ValueError):
            continue
    status_code = payload.get("status_code")
    try:
        return status_code is not None and int(status_code) >= 400
    except (TypeError, ValueError):
        return False




def _messages_since_latest_human(messages: list[object]) -> list[object]:
    start = _latest_human_index(messages) + 1
    return messages[start:] if start > 0 else messages


def _tool_call_args_signature(tool_name: str, args: object) -> str:
    try:
        encoded_args = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        encoded_args = str(args)
    return f"{tool_name}:{encoded_args}"


def _tool_call_by_id(messages: list[object], tool_call_id: str | None) -> tuple[str | None, object | None]:
    if not tool_call_id:
        return None, None
    for message in reversed(messages):
        if getattr(message, "type", None) != "ai":
            continue
        for call in getattr(message, "tool_calls", None) or []:
            if call.get("id") == tool_call_id:
                return call.get("name"), call.get("args")
    return None, None


def _tool_error_entries(messages: list[object], *, include_recovery_guards: bool = False) -> list[ToolErrorEntry]:
    start = _latest_human_index(messages) + 1
    entries: list[ToolErrorEntry] = []
    scoped_messages = messages[start:]
    for message in scoped_messages:
        if not isinstance(message, ToolMessage) or not _tool_message_is_error(message):
            continue
        if _is_write_todos_duplicate_guard(message):
            continue
        if _is_recovery_guard_message(message) and not include_recovery_guards:
            continue
        tool_name = getattr(message, "name", None)
        args: object | None = None
        if not tool_name:
            tool_name, args = _tool_call_by_id(scoped_messages, getattr(message, "tool_call_id", None))
        elif args is None:
            _, args = _tool_call_by_id(scoped_messages, getattr(message, "tool_call_id", None))
        resolved_name = str(tool_name or "unknown")
        entries.append(
            ToolErrorEntry(
                tool_name=resolved_name,
                content=_message_text(message),
                signature=_tool_call_args_signature(resolved_name, args),
            )
        )
    return entries


def _recent_consecutive_errors(messages: list[object], *, include_recovery_guards: bool = False) -> list[ToolErrorEntry]:
    start = _latest_human_index(messages) + 1
    scoped_messages = messages[start:]
    entries: list[ToolErrorEntry] = []
    for message in reversed(scoped_messages):
        if isinstance(message, ToolMessage):
            if _is_recovery_guard_message(message) and not include_recovery_guards:
                continue
            if not _tool_message_is_error(message):
                break
            tool_name = getattr(message, "name", None)
            args: object | None = None
            if not tool_name:
                tool_name, args = _tool_call_by_id(scoped_messages, getattr(message, "tool_call_id", None))
            elif args is None:
                _, args = _tool_call_by_id(scoped_messages, getattr(message, "tool_call_id", None))
            resolved_name = str(tool_name or "unknown")
            entries.append(
                ToolErrorEntry(
                    tool_name=resolved_name,
                    content=_message_text(message),
                    signature=_tool_call_args_signature(resolved_name, args),
                )
            )
            continue
        if getattr(message, "type", None) == "ai" and getattr(message, "tool_calls", None):
            continue
        if getattr(message, "type", None) == "system":
            continue
        break
    return list(reversed(entries))


def _consecutive_recent_tool_signatures(messages: list[object], limit: int = 30) -> list[str]:
    """Walk back from the latest AI tool-call message and collect, in
    reverse chronological order, the tool-call signatures issued in the most
    recent contiguous AI tool-call block(s).

    Stops at the first non-tool, non-AI-with-tool-calls boundary or after
    `limit` signatures, whichever comes first.
    """
    start = _latest_human_index(messages) + 1
    scoped = messages[start:]
    signatures: list[str] = []
    for message in reversed(scoped):
        kind = getattr(message, "type", None)
        if isinstance(message, ToolMessage):
            continue
        if kind == "ai":
            for call in getattr(message, "tool_calls", None) or []:
                signatures.append(_tool_call_args_signature(str(call.get("name") or "unknown"), call.get("args")))
        elif kind == "system":
            continue
        else:
            break
        if len(signatures) >= limit:
            break
    return signatures


def _duplicate_signature_recent_count(signatures: list[str], current_signature: str) -> int:
    """Count how many of the recent signatures match `current_signature`.

    Considers the whole recent window (since the latest human turn) so that
    interleaved duplicates from parallel multi-tool calls are detected.
    """
    return sum(1 for sig in signatures if sig == current_signature)


def _most_common_tool_count(entries: list[ToolErrorEntry], tool_name: str) -> int:
    return sum(1 for entry in entries if entry.tool_name == tool_name)


def _planning_noop_guard_count(messages: list[object]) -> int:
    return sum(
        1
        for message in _messages_since_latest_human(messages)
        if isinstance(message, ToolMessage) and _is_planning_noop_guard(message)
    )


def _planning_loop_handoff_answer(messages: list[object], *, dup_count: int) -> str:
    evidence_tools: list[str] = []
    for message in _messages_since_latest_human(messages):
        if isinstance(message, ToolMessage):
            name = str(getattr(message, "name", "") or "")
            if name and name != "write_todos":
                evidence_tools.append(name)
    evidence_summary = "none" if not evidence_tools else ", ".join(sorted(set(evidence_tools)))
    return "\n".join(
        [
            "Planning loop recovery checkpoint: repeated write_todos calls are no longer useful.",
            "",
            "Observed cause:",
            f"- The same write_todos arguments were requested at least {dup_count} times.",
            "- Prior planning updates were already treated as no-ops, so more write_todos calls would not add evidence.",
            f"- Non-planning evidence tools completed in this turn: {evidence_summary}.",
            "",
            "This is not task completion and not a hard stop. Continue by gathering evidence, answering from existing evidence, or asking exactly one focused question if required input is missing.",
        ]
    )

def _latest_human_text(messages: list[object]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return _message_text(message).strip()
    return ""


def _soft_constraint_reflection_already_injected(messages: list[object], kind: str) -> bool:
    needle = f"kind: {kind}"
    return any(
        isinstance(message, SystemMessage) and _SELF_CONSTRAINT_MARKER in _message_text(message) and needle in _message_text(message)
        for message in _messages_since_latest_human(messages)
    )


def _self_constraint_memory_guidance(*, kind: str, observation: str, suggested_lesson: str, user_goal: str) -> str:
    goal = user_goal or "current user goal"
    return "\n".join(
        [
            _SELF_CONSTRAINT_MARKER,
            f"kind: {kind}",
            "This is advisory guidance for model self-regulation, not a hard stop and not task completion.",
            "Observed pattern:",
            f"- {observation}",
            "Self-iteration protocol:",
            "- If memory tools are available, call search_memory for similar prior lessons before repeating the same tool pattern.",
            "- If this pattern is new or recurring, call archival_memory_insert with a concise lesson and tags such as runtime_self_constraint and tool_policy.",
            "- If the lesson is broadly durable, consider memory_block_upsert(label=\"tool_policy\", ...) to update the soft tool policy in core memory.",
            "- Then choose the next step yourself: answer from existing evidence, change strategy, ask for missing input, or continue only if a specific evidence gap remains.",
            "Suggested memory query:",
            f"- {kind} {goal}",
            "Suggested lesson draft:",
            f"- {suggested_lesson}",
            "</runtime_self_constraint_reflection>",
        ]
    )



def _truncate_error(text: str, limit: int = 700) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "..."


def _recovery_stage(error_count: int) -> str:
    if error_count <= 0:
        return "none"
    if error_count < 3:
        return "repair"
    if error_count < 6:
        return "alternate"
    if error_count < 9:
        return "discover"
    return "final"


def _recovery_instruction(entries: list[ToolErrorEntry]) -> str | None:
    if not entries:
        return None
    error_count = len(entries)
    stage = _recovery_stage(error_count)
    last_error = entries[-1]
    tool_counts = Counter(entry.tool_name for entry in entries)
    common_tools = ", ".join(f"{name}={count}" for name, count in tool_counts.most_common(3))
    lines = [
        "<tool_recovery_policy>",
        "工具调用刚刚失败。你必须按 OctoAgent 的恢复策略继续，而不是反复提交相同错误。",
        f"- 当前阶段：{stage}",
        f"- 本轮累计工具错误：{error_count}",
        f"- 错误工具计数：{common_tools}",
        f"- 最近失败工具：{last_error.tool_name}",
        f"- 最近错误摘要：{_truncate_error(last_error.content)}",
    ]
    if stage == "repair":
        lines.extend(
            [
                "- 动作：先检查工具 schema、参数名、路径、权限和依赖；修正参数后才可以重试。",
                "- 如果是 sandbox 文件/命令工具缺少 description，重新调用时带上简短 description；系统也会做保底补齐。",
            ]
        )
        if last_error.tool_name == "web_fetch":
            lines.extend(
                [
                    "- web_fetch 专项：确认 URL 是否来自用户或搜索结果、是否为公开 http/https 页面、是否被站点限流/超时或重定向到受限地址。",
                    "- 如果目标是动态接口、登录墙或反爬页面，优先换用同主题的公开资料页。",
                ]
            )
    elif stage == "alternate":
        lines.extend(
            [
                "- 动作：同类错误已达到三次，切换到不同工具或不同实现路径。",
                "- 不要再次调用同一个失败工具，除非参数、目标或执行方式已经发生实质变化。",
            ]
        )
        if last_error.tool_name == "web_fetch":
            lines.extend(
                [
                    "- web_fetch 已连续失败：不要继续抓取同一个 URL。改用 web_search 寻找替代来源，或改用 read_webpage 抓取不同公开页面。",
                    "- 如果错误是 private/internal network，视为安全拦截；不要尝试绕过，只能换公开来源。",
                ]
            )
    elif stage == "discover":
        lines.extend(
            [
                f"- 动作：继续失败后，先查找可替代能力。优先 {_discovery_guidance_zh()}。",
                "- 如果发现可用替代工具，使用替代工具完成任务；如果需要安装能力，先说明风险和依赖。",
            ]
        )
    else:
        lines.extend(
            [
                "- Action: repeated tool failures reached the final recovery review point.",
                "- This is still advisory recovery guidance, not a hard stop and not task completion.",
                "- Do not repeat the same failing call. Switch strategy, use a different capability/source, ask for missing input, or explain the specific external blocker.",
                "- If enough evidence already exists, produce a substantive answer from that evidence; otherwise keep the task recoverable and name the next safe step.",
            ]
        )
    lines.append("</tool_recovery_policy>")
    return "\n".join(lines)


def _tool_failure_answer(entries: list[ToolErrorEntry]) -> str:
    lines = [
        "Tool recovery review: repeated tool calls failed and the same failing path should not be retried.",
        "",
        "Failure evidence:",
    ]
    for index, entry in enumerate(entries[-6:], start=1):
        lines.append(f"{index}. `{entry.tool_name}`: {_truncate_error(entry.content, 360)}")
    web_fetch_errors = [entry for entry in entries if entry.tool_name == "web_fetch"]
    lines.extend(
        [
            "",
            "Recovery status: this is not task completion and not a runtime hard stop.",
            "Safe next step: change tool/source/arguments, ask for missing operator input, or report the specific external blocker while keeping the task recoverable.",
            "Do not claim that the recovery policy itself stopped the task.",
        ]
    )
    if web_fetch_errors:
        lines.append(
            "web_fetch note: if the target URL times out, blocks bots, requires login, is a dynamic API, or triggers private/internal network protection, use a different public source instead of bypassing safety controls."
        )
    return "\n".join(lines)

def _recovery_lesson_hash(entries: list[ToolErrorEntry]) -> str:
    normalized = "|".join(f"{entry.tool_name}:{_truncate_error(entry.content, 180)}" for entry in entries[-6:])
    return hashlib.sha1(normalized.encode("utf-8", errors="replace")).hexdigest()[:16]


def _recovery_lesson_query(entries: list[ToolErrorEntry]) -> str:
    if not entries:
        return "tool recovery repeated failures"
    tools = " ".join(entry.tool_name for entry in entries[-6:])
    errors = " ".join(_truncate_error(entry.content, 160) for entry in entries[-3:])
    return f"tool recovery repeated failures {tools} {errors}"


def _build_recovery_lesson(entries: list[ToolErrorEntry]) -> tuple[str, dict[str, Any]] | None:
    if len(entries) < 3:
        return None
    lesson_hash = _recovery_lesson_hash(entries)
    tool_counts = Counter(entry.tool_name for entry in entries)
    dominant_tool, dominant_count = tool_counts.most_common(1)[0]
    stage = _recovery_stage(len(entries))
    recent_errors = "\n".join(f"- {entry.tool_name}: {_truncate_error(entry.content, 240)}" for entry in entries[-4:])
    content = "\n".join(
        [
            "Tool recovery lesson (soft constraint).",
            f"Pattern: repeated tool failures in one turn; stage={stage}; dominant_tool={dominant_tool}; dominant_count={dominant_count}.",
            "Observed errors:",
            recent_errors,
            (
                "Experience summary: after three failures, inspect schema/arguments/settings "
                "and switch tool, source, or implementation path instead of repeating. If failures persist, "
                "avoid repeating failing calls and communicate the blocker, evidence, and needed user/operator input."
            ),
            "This lesson is advisory memory; it is not an OOM or task hard stop.",
        ]
    )
    metadata = {
        "source": "tool_budget_middleware",
        "kind": "tool_recovery_lesson",
        "lesson_hash": lesson_hash,
        "stage": stage,
        "tool_names": sorted(tool_counts),
        "dominant_tool": dominant_tool,
        "error_count": len(entries),
        "confidence": 0.82,
    }
    return content, metadata


def _record_recovery_lesson(entries: list[ToolErrorEntry]) -> str | None:
    built = _build_recovery_lesson(entries)
    if built is None:
        return None
    content, metadata = built
    lesson_hash = str(metadata["lesson_hash"])
    with _recovery_lesson_cache_lock:
        if lesson_hash in _recovery_lesson_hashes:
            return None
    try:
        from src.agents.memory.system_rag_store import get_system_rag_store

        store = get_system_rag_store()
        for existing in store.list_entries(namespace="skill_evolution", limit=200):
            if isinstance(existing.metadata, dict) and existing.metadata.get("lesson_hash") == lesson_hash:
                with _recovery_lesson_cache_lock:
                    _recovery_lesson_hashes.add(lesson_hash)
                return None
        entry_id = store.add("skill_evolution", content, agent_name="ToolBudgetMiddleware", metadata=metadata)
        with _recovery_lesson_cache_lock:
            _recovery_lesson_hashes.add(lesson_hash)
            if len(_recovery_lesson_hashes) > _RECOVERY_LESSON_CACHE_MAX:
                _recovery_lesson_hashes.clear()
                _recovery_lesson_hashes.add(lesson_hash)
        return entry_id or None
    except Exception:
        return None


def _retrieve_recovery_lessons(entries: list[ToolErrorEntry], *, limit: int = 3) -> list[str]:
    if len(entries) < 1:
        return []
    try:
        from src.agents.memory.system_rag_store import get_system_rag_store

        store = get_system_rag_store()
        results = store.search(_recovery_lesson_query(entries), namespace="skill_evolution", top_k=limit)
    except Exception:
        return []
    lessons: list[str] = []
    for result in results:
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        if metadata.get("kind") != "tool_recovery_lesson":
            continue
        text = _truncate_error(str(result.content or ""), 520)
        if text:
            lessons.append(text)
    return lessons[:limit]


def _append_recovery_memory(instruction: str, lessons: list[str]) -> str:
    if not lessons:
        return instruction
    lines = [instruction, "<tool_recovery_memory>", "相关历史经验（来自 skill_evolution 记忆，软约束）："]
    for index, lesson in enumerate(lessons, start=1):
        lines.append(f"{index}. {lesson}")
    lines.extend(
        [
            "本轮请把新的失败模式也总结成经验；若工具继续失败，应向用户说明阻塞、已尝试路径和需要的配置/输入。",
            "</tool_recovery_memory>",
        ]
    )
    return "\n".join(lines)


def _alternate_tool_guidance(tool_name: str, tool_error_count: int) -> str:
    if tool_name == "web_fetch":
        return (
            f"Error: tool 'web_fetch' has already failed {tool_error_count} times in this turn. "
            "Recovery policy requires switching to a different source or implementation path. "
            "Do not fetch the same URL again. Use web_search to find alternative public references, "
            "or use read_webpage on a different public URL. If the error says private/internal network, "
            "it is an SSRF safety block and must not be bypassed."
        )
    return f"Error: tool '{tool_name}' has already failed {tool_error_count} times in this turn. Recovery policy requires switching to a different tool or implementation path."


def _auto_description(tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "bash":
        command = str(args.get("command") or "").strip()
        return f"Run command: {command[:80]}" if command else "Run shell command"
    if tool_name == "ls":
        return f"List directory: {str(args.get('path') or '').strip()[:80]}"
    if tool_name == "read_file":
        return f"Read file: {str(args.get('path') or '').strip()[:80]}"
    if tool_name == "write_file":
        return f"Write file: {str(args.get('path') or '').strip()[:80]}"
    if tool_name == "str_replace":
        return f"Edit file: {str(args.get('path') or '').strip()[:80]}"
    return "Tool call auto-description"


def _tool_texts(messages: list[object]) -> list[str]:
    return [_message_text(message) for message in _messages_since_latest_human(messages) if isinstance(message, ToolMessage)]


def _parse_soft_tool_budget(text: str) -> int | None:
    for pattern in _SOFT_BUDGET_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            value = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _runtime_soft_tool_budget(context: dict[str, Any]) -> int | None:
    candidates: list[Any] = [
        context.get("tool_soft_budget_messages"),
        context.get("soft_tool_budget_messages"),
        context.get("max_tool_messages"),
    ]
    policy = context.get("tool_budget_policy")
    if isinstance(policy, dict):
        candidates.extend(
            [
                policy.get("soft_tool_messages"),
                policy.get("soft_tool_calls"),
                policy.get("max_tool_messages"),
            ]
        )
    governance = context.get("session_governance")
    if isinstance(governance, dict):
        candidates.extend(
            [
                governance.get("soft_tool_messages"),
                governance.get("tool_call_budget"),
            ]
        )

    for candidate in candidates:
        try:
            value = int(candidate)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _system_memory_soft_tool_budget() -> int | None:
    # Disabled by default (2026-05-16): memory-derived soft budgets caused
    # premature task termination when memory entries contained numeric values
    # that were parsed as tool call limits.
    if not _SOFT_BUDGET_FROM_MEMORY_ENABLED:
        return None
    global _soft_budget_cache
    now = time.monotonic()
    with _soft_budget_cache_lock:
        cached_at, cached_value = _soft_budget_cache
        if now - cached_at < _SOFT_BUDGET_MEMORY_TTL_SECONDS:
            return cached_value

    budget: int | None = None
    try:
        from src.agents.memory.system_rag_store import get_system_rag_store

        store = get_system_rag_store()
        for namespace in ("system_insight", "skill_evolution", "conversation_summary"):
            for entry in store.list_entries(namespace=namespace, limit=20):
                parsed = _parse_soft_tool_budget(str(entry.content or ""))
                if parsed is not None:
                    budget = parsed
                    break
            if budget is not None:
                break
    except Exception:
        budget = None

    with _soft_budget_cache_lock:
        _soft_budget_cache = (now, budget)
    return budget


def _soft_tool_budget_guidance(tool_count: int, budget: int) -> str:
    return "\n".join(
        [
            "<tool_soft_budget_policy>",
            "长期系统记忆或运行时上下文建议当前任务进入工具使用复盘点。",
            f"- 本轮已完成工具结果数：{tool_count}",
            f"- 软预算建议值：{budget}",
            "- 这是软上限，不是硬停止；如果任务仍需真实检查、修复或验证，可以继续调用必要工具。",
            "- 继续前请先判断：已有证据是否足够、是否存在重复无效路径、下一次工具调用是否能带来新的有效信息。",
            "- 不要向用户声称已经达到系统硬上限；只有确实完成或遇到外部阻塞时才总结。",
            "</tool_soft_budget_policy>",
        ]
    )


def _research_tool_counts(messages: list[object]) -> tuple[int, int, int]:
    total = 0
    fetches = 0
    substantive = 0
    for message in _messages_since_latest_human(messages):
        if not isinstance(message, ToolMessage):
            continue
        tool_name = str(getattr(message, "name", "") or "")
        if tool_name not in _WEB_RESEARCH_TOOLS:
            continue
        total += 1
        if tool_name in {"web_fetch", "web_fetch_heavy", "read_webpage"}:
            fetches += 1
        text = _message_text(message).strip()
        if not _tool_message_is_error(message) and len(text) >= _RESEARCH_SUBSTANTIVE_CHARS:
            substantive += 1
    return total, fetches, substantive


def _research_closure_needed(messages: list[object]) -> tuple[bool, int, int, int]:
    total, fetches, substantive = _research_tool_counts(messages)
    if substantive < _RESEARCH_CLOSURE_MIN_SUBSTANTIVE:
        return False, total, fetches, substantive
    if total >= _RESEARCH_CLOSURE_TOOL_LIMIT or fetches >= _RESEARCH_CLOSURE_FETCH_LIMIT:
        return True, total, fetches, substantive
    return False, total, fetches, substantive


def _research_closure_already_injected(messages: list[object]) -> bool:
    for message in _messages_since_latest_human(messages):
        if isinstance(message, SystemMessage) and "<research_closure_policy>" in _message_text(message):
            return True
        if isinstance(message, ToolMessage) and getattr(message, "additional_kwargs", {}).get(_RESEARCH_CLOSURE_GUARD_KEY):
            return True
    return False


def _research_closure_guidance(total: int, fetches: int, substantive: int) -> str:
    return "\n".join(
        [
            "<research_closure_policy>",
            "Web research has reached the evidence sufficiency threshold for this turn.",
            f"- Web research tool results collected: {total}",
            f"- Fetch/read results collected: {fetches}",
            f"- Substantive evidence-bearing results: {substantive}",
            "- Prefer not to call web_search, web_fetch, web_fetch_heavy, scrapling_fetch, or read_webpage again unless you can name a specific unresolved evidence gap.",
            "- Produce the final user-facing report now from the evidence already in the conversation.",
            "- If important gaps remain, state them explicitly as limitations instead of expanding the crawl.",
            "</research_closure_policy>",
        ]
    )


def _research_closure_active(runtime_state: dict[str, Any]) -> bool:
    closure = runtime_state.get("research_closure")
    return isinstance(closure, dict) and closure.get("status") == "must_finalize"


def _research_closure_guard_count(messages: list[object]) -> int:
    return sum(
        1
        for message in _messages_since_latest_human(messages)
        if isinstance(message, ToolMessage) and getattr(message, "additional_kwargs", {}).get(_RESEARCH_CLOSURE_GUARD_KEY)
    )


def _research_evidence_already_compacted(messages: list[object]) -> bool:
    return any(
        isinstance(message, ToolMessage) and getattr(message, "additional_kwargs", {}).get(_RESEARCH_EVIDENCE_COMPACTED_KEY)
        for message in _messages_since_latest_human(messages)
    )


def _compact_research_tool_message(message: ToolMessage) -> ToolMessage:
    text = re.sub(r"\s+", " ", _message_text(message)).strip()
    if len(text) <= _RESEARCH_COMPACT_CHARS:
        excerpt = text
    else:
        excerpt = text[:_RESEARCH_COMPACT_CHARS].rstrip() + "..."
    urls = list(dict.fromkeys(re.findall(r"https?://[^\s)\]}>'\"]+", text)))[:5]
    lines = [
        "[Compacted web evidence for final report]",
        f"tool: {getattr(message, 'name', '') or 'web'}",
        f"original_chars: {len(text)}",
        f"excerpt: {excerpt}",
    ]
    if urls:
        lines.append("urls: " + ", ".join(urls))
    return message.model_copy(
        update={
            "content": "\n".join(lines),
            "additional_kwargs": {
                **getattr(message, "additional_kwargs", {}),
                _RESEARCH_EVIDENCE_COMPACTED_KEY: True,
            },
        }
    )


def _compact_research_evidence_for_final(messages: list[object]) -> tuple[list[object], int]:
    patched: list[object] = []
    compacted = 0
    for message in messages:
        if isinstance(message, ToolMessage) and str(getattr(message, "name", "") or "") in _WEB_RESEARCH_TOOLS:
            patched.append(_compact_research_tool_message(message))
            compacted += 1
            continue
        patched.append(message)
    return patched, compacted


def _research_final_only_guidance(compacted: int) -> str:
    return "\n".join(
        [
            "<research_final_answer_mode>",
            "Research evidence has been compacted for the final response to avoid context/time blow-up.",
            f"- Compacted web evidence messages: {compacted}",
            "- Prefer to avoid more tools now, including web_search, web_fetch, web_fetch_heavy, scrapling_fetch, or read_webpage, unless one specific missing evidence gap is named first.",
            "- Produce a user-facing Chinese report directly from the current user goal, compacted evidence, and earlier conversation.",
            "- Base the report only on observable tool evidence and stated user requirements.",
            "- Do not introduce a domain, vendor list, market category, or recommendation frame that is not present in the current user goal or evidence.",
            "- If evidence is incomplete, state the gaps and limitations explicitly instead of inventing missing facts.",
            "</research_final_answer_mode>",
        ]
    )



class ToolBudgetMiddleware(AgentMiddleware[AgentState]):
    """Recover tool failures and provide memory-derived soft budget guidance.

    Recovery policy:
    - first errors: guide the model to inspect schema/arguments and retry safely;
    - after three errors: return recovery feedback asking for a different tool/path;
    - after six errors: return capability/tool/settings discovery feedback;
    - after nine errors: inject memory-backed self-iteration guidance instead of finalizing.

    Normal successful tool use has no default hard per-turn ceiling. If runtime
    context or long-term system memory defines a tool budget, it is treated as a
    soft review point and injected as hidden guidance instead of stopping tools.
    """

    def __init__(
        self,
        max_tool_messages: int | None = None,
        switch_tool_errors: int = 3,
        discover_tool_errors: int = 6,
        final_failure_errors: int = 9,
    ):
        super().__init__()
        self.max_tool_messages = max_tool_messages
        self.switch_tool_errors = switch_tool_errors
        self.discover_tool_errors = discover_tool_errors
        self.final_failure_errors = final_failure_errors

    def _effective_soft_tool_budget(self, runtime: Runtime | None) -> int | None:
        context = runtime.context if runtime is not None and runtime.context else {}
        runtime_budget = _runtime_soft_tool_budget(context)
        if runtime_budget is not None:
            return runtime_budget
        memory_budget = _system_memory_soft_tool_budget()
        if memory_budget is not None:
            return memory_budget
        return self.max_tool_messages

    def _inject_recovery_guidance(self, state: AgentState, runtime: Runtime | None) -> dict | None:
        messages = list(state.get("messages", []))
        if not messages:
            return None
        runtime_state_current = dict(state.get("runtime") or {})
        if _research_closure_active(runtime_state_current) and not _research_evidence_already_compacted(messages):
            compacted_messages, compacted = _compact_research_evidence_for_final(messages)
            runtime_state_current["research_evidence_compaction"] = {
                "status": "compacted_for_final",
                "messages": compacted,
                "max_chars_per_message": _RESEARCH_COMPACT_CHARS,
            }
            return {
                "messages": [*compacted_messages, SystemMessage(content=_research_final_only_guidance(compacted))],
                "runtime": runtime_state_current,
            }

        planning_noop_count = _planning_noop_guard_count(messages)
        if planning_noop_count >= _PLANNING_LOOP_FINALIZE_DUP and not _soft_constraint_reflection_already_injected(messages, "planning_noop_loop"):
            runtime_state = dict(state.get("runtime") or {})
            runtime_state["self_feedback_action"] = "self_iterate_planning_noop_loop_with_memory"
            runtime_state["tool_recovery"] = {
                "stage": "planning_loop_soft_constraint",
                "tool": "write_todos",
                "noop_guard_count": planning_noop_count,
                "hard_stop": False,
            }
            return {
                "messages": [
                    SystemMessage(
                        content=_self_constraint_memory_guidance(
                            kind="planning_noop_loop",
                            observation=f"write_todos planning updates were treated as no-ops {planning_noop_count} times in this turn.",
                            suggested_lesson=(
                                "When write_todos repeats without changing state, summarize the loop into memory "
                                "and switch to evidence gathering, asking a clarifying question, or answering from "
                                "available evidence instead of rewriting the same plan."
                            ),
                            user_goal=_latest_human_text(messages),
                        )
                    )
                ],
                "runtime": runtime_state,
            }

        if _research_closure_active(runtime_state_current) and not _soft_constraint_reflection_already_injected(messages, "research_closure_loop"):
            research_total, research_fetches, research_substantive = _research_tool_counts(messages)
            guard_count = _research_closure_guard_count(messages)
            extra_total = research_total >= (_RESEARCH_CLOSURE_TOOL_LIMIT + _RESEARCH_CLOSURE_SELF_REFLECT_EXTRA_TOOLS)
            extra_fetches = research_fetches >= (_RESEARCH_CLOSURE_FETCH_LIMIT + _RESEARCH_CLOSURE_SELF_REFLECT_EXTRA_TOOLS)
            if guard_count > 0 or extra_total or extra_fetches:
                runtime_state = dict(state.get("runtime") or {})
                runtime_state["self_feedback_action"] = "self_iterate_research_closure_loop_with_memory"
                runtime_state["research_closure_reflection"] = {
                    "tool_messages": research_total,
                    "fetch_messages": research_fetches,
                    "substantive_results": research_substantive,
                    "closure_guards": guard_count,
                    "hard_stop": False,
                }
                guidance = _self_constraint_memory_guidance(
                    kind="research_closure_loop",
                    observation=(
                        f"web research already produced {research_total} tool results "
                        f"({research_fetches} fetch/read, {research_substantive} substantive); "
                        "model continued calling research tools after the closure threshold."
                    ),
                    suggested_lesson=(
                        "Once web evidence is sufficient, write the final report from collected "
                        "results instead of issuing more searches; record any remaining gaps as "
                        "explicit limitations."
                    ),
                    user_goal=_latest_human_text(messages),
                )
                return {
                    "messages": [SystemMessage(content=guidance)],
                    "runtime": runtime_state,
                }

        closure_needed, research_total, research_fetches, research_substantive = _research_closure_needed(messages)
        if closure_needed and not _research_closure_already_injected(messages):
            runtime_state = dict(state.get("runtime") or {})
            runtime_state["research_closure"] = {
                "status": "must_finalize",
                "tool_messages": research_total,
                "fetch_messages": research_fetches,
                "substantive_results": research_substantive,
                "tool_limit": _RESEARCH_CLOSURE_TOOL_LIMIT,
                "fetch_limit": _RESEARCH_CLOSURE_FETCH_LIMIT,
            }
            return {
                "messages": [SystemMessage(content=_research_closure_guidance(research_total, research_fetches, research_substantive))],
                "runtime": runtime_state,
            }

        if not isinstance(messages[-1], ToolMessage):
            return None
        entries = _recent_consecutive_errors(messages, include_recovery_guards=True)
        if len(entries) >= self.final_failure_errors and not _soft_constraint_reflection_already_injected(messages, "tool_failure_loop"):
            lesson_entry_id = _record_recovery_lesson(entries)
            lessons = _retrieve_recovery_lessons(entries)
            runtime_state = dict(state.get("runtime") or {})
            runtime_state["self_feedback_action"] = "self_iterate_tool_failure_loop_with_memory"
            runtime_state["tool_recovery"] = {
                "stage": "final_soft_constraint",
                "error_count": len(entries),
                "last_tool": entries[-1].tool_name,
                "hard_stop": False,
                "memory_lesson_recorded": bool(lesson_entry_id),
                "memory_lessons_injected": len(lessons),
            }
            guidance = _self_constraint_memory_guidance(
                kind="tool_failure_loop",
                observation=(
                    f"{len(entries)} consecutive tool failures occurred in this turn; "
                    f"latest failing tool is {entries[-1].tool_name}."
                ),
                suggested_lesson=(
                    "When a turn accumulates repeated tool failures, use memory tools to summarize the pattern, "
                    "then change strategy or explain the specific blocker instead of treating recovery guidance as task completion."
                ),
                user_goal=_latest_human_text(messages),
            )
            if lessons:
                guidance = _append_recovery_memory(guidance, lessons)
            return {"messages": [SystemMessage(content=guidance)], "runtime": runtime_state}

        instruction = _recovery_instruction(entries)
        if instruction is not None:
            lesson_entry_id = _record_recovery_lesson(entries)
            lessons = _retrieve_recovery_lessons(entries)
            instruction = _append_recovery_memory(instruction, lessons)
            runtime_state = dict(state.get("runtime") or {})
            runtime_state["tool_recovery"] = {
                "stage": _recovery_stage(len(entries)),
                "error_count": len(entries),
                "last_tool": entries[-1].tool_name,
                "memory_lesson_recorded": bool(lesson_entry_id),
                "memory_lessons_injected": len(lessons),
            }
            return {"messages": [SystemMessage(content=instruction)], "runtime": runtime_state}

        tool_texts = _tool_texts(messages)
        soft_budget = self._effective_soft_tool_budget(runtime)
        if soft_budget is None or len(tool_texts) < soft_budget:
            return None
        if any(isinstance(message, SystemMessage) and "<tool_soft_budget_policy>" in _message_text(message) for message in _messages_since_latest_human(messages)):
            return None
        runtime_state = dict(state.get("runtime") or {})
        runtime_state["tool_soft_budget"] = {
            "status": "advisory",
            "tool_messages": len(tool_texts),
            "soft_budget": soft_budget,
        }
        return {
            "messages": [SystemMessage(content=_soft_tool_budget_guidance(len(tool_texts), soft_budget))],
            "runtime": runtime_state,
        }

    def _with_auto_description(self, request: ToolCallRequest) -> ToolCallRequest:
        tool_name = request.tool.name if request.tool else request.tool_call.get("name")
        if tool_name not in _AUTO_DESCRIPTION_TOOLS:
            return request
        args = request.tool_call.get("args")
        if not isinstance(args, dict):
            return request
        if str(args.get("description") or "").strip():
            return request
        next_args = {**args, "description": _auto_description(str(tool_name), args)}
        return request.override(tool_call={**request.tool_call, "args": next_args})

    def _blocked_repeated_tool_message(self, request: ToolCallRequest) -> ToolMessage | Command | None:
        messages = list((request.state or {}).get("messages", [])) if isinstance(request.state, dict) else []
        tool_name_current = request.tool.name if request.tool else str(request.tool_call.get("name") or "unknown")
        current_sig = _tool_call_args_signature(tool_name_current, request.tool_call.get("args"))
        recent_signatures = _consecutive_recent_tool_signatures(messages, limit=60)
        dup_count = _duplicate_signature_recent_count(recent_signatures, current_sig)
        if (
            dup_count >= _DUPLICATE_TOOL_CALL_HARD_LIMIT
            and tool_name_current != "write_todos"
        ):
            logger.warning(
                "ToolBudget: hard-stopping duplicate tool loop tool=%s dup=%d limit=%d",
                tool_name_current,
                dup_count,
                _DUPLICATE_TOOL_CALL_HARD_LIMIT,
            )
            hard_stop_tool_message = ToolMessage(
                content=(
                    f"Tool loop hard-stop: `{tool_name_current}` has been called with identical "
                    f"arguments {dup_count} times in this turn despite repeated recovery hints. "
                    "Aborting tool execution to break the loop."
                ),
                name=tool_name_current,
                tool_call_id=request.tool_call.get("id"),
                status="error",
                additional_kwargs={
                    _RECOVERY_GUARD_KEY: True,
                    _TOOL_LOOP_HARD_STOP_KEY: True,
                },
            )
            summary_message = AIMessage(
                content=(
                    f"检测到工具调用陷入循环：`{tool_name_current}` 在本轮已被相同参数重复调用 "
                    f"{dup_count} 次，尽管系统多次提示更换策略，模型仍持续重复同一调用。"
                    "为避免继续消耗资源，已自动中止本轮。\n\n"
                    "建议：请基于已有上下文重新发起请求，或在提示中明确指出不要重复同一工具调用，"
                    "并提供更具体的目标（更换工具、修改参数或缩小范围）。"
                ),
            )
            return Command(
                update={"messages": [hard_stop_tool_message, summary_message]},
                goto=END,
            )
        entries = _tool_error_entries(messages)
        closure_needed, research_total, research_fetches, research_substantive = _research_closure_needed(messages)
        if _RESEARCH_CLOSURE_BLOCK_WEB_TOOLS and closure_needed and tool_name_current in _WEB_RESEARCH_TOOLS:
            return ToolMessage(
                content=(
                    "Research collection skipped: enough web evidence has already been gathered in this turn "
                    f"({research_total} web results, {research_fetches} fetch/read results, "
                    f"{research_substantive} substantive results). Do not call more web research tools. "
                    "Produce the final report now from the existing evidence, and mention any remaining limitations explicitly."
                ),
                name=tool_name_current,
                tool_call_id=request.tool_call.get("id"),
                status="success",
                additional_kwargs={_RESEARCH_CLOSURE_GUARD_KEY: True},
            )
        exhausted_entries = _tool_error_entries(messages, include_recovery_guards=True)
        if not entries:
            if dup_count >= _DUPLICATE_TOOL_CALL_LIMIT:
                if tool_name_current == "write_todos":
                    return _planning_noop_guard_message(
                        dup_count=dup_count,
                        tool_call_id=request.tool_call.get("id"),
                    )
                return _recovery_guard_message(
                    content=(
                        f"Error: this exact tool call ({tool_name_current} with identical arguments) "
                        f"has already been tried {dup_count} times in this turn with the same result. "
                        "This is a recovery hint, not a task hard stop: do not repeat this call. "
                        "Change the arguments materially, switch to a different tool/source, or explain the blockage to the user."
                    ),
                    name=tool_name_current,
                    tool_call_id=request.tool_call.get("id"),
                )
            return None

        tool_name = tool_name_current
        tool_error_count = _most_common_tool_count(entries, tool_name)
        total_errors = len(entries)
        if _TOOL_RECOVERY_LEGACY_BLOCK_FINAL_TOOLS_REQUESTED and len(exhausted_entries) >= self.final_failure_errors:
            logger.info(
                "Ignoring legacy OCTO_TOOL_RECOVERY_BLOCK_FINAL_TOOLS hard-stop request; tool recovery is advisory only."
            )
        if total_errors >= self.discover_tool_errors and tool_name not in _discovery_tools():
            return _recovery_guard_message(
                content=(
                    f"Error: this turn has {total_errors} tool failures. "
                    f"Recovery policy requires capability discovery / tool/settings review now: {_discovery_guidance_en()}. "
                    "Do not keep calling failing tools without first checking alternatives or configuration."
                ),
                name=tool_name,
                tool_call_id=request.tool_call.get("id"),
            )
        if tool_error_count >= self.switch_tool_errors:
            return _recovery_guard_message(
                content=_alternate_tool_guidance(tool_name, tool_error_count),
                name=tool_name,
                tool_call_id=request.tool_call.get("id"),
            )
        return None

    @staticmethod
    def _mark_error_result(result: ToolMessage | Command) -> ToolMessage | Command:
        if not isinstance(result, ToolMessage):
            return result
        if getattr(result, "status", None) == "error":
            return result
        text = _message_text(result).strip().lower()
        if not (text.startswith(_ERROR_PREFIXES) or any(marker in text for marker in _ERROR_MARKERS) or _json_tool_payload_is_error(text)):
            return result
        return result.model_copy(update={"status": "error"})

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._inject_recovery_guidance(state, runtime)

    @override
    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._inject_recovery_guidance(state, runtime)

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        blocked = self._blocked_repeated_tool_message(request)
        if blocked is not None:
            return blocked
        request = self._with_auto_description(request)
        return self._mark_error_result(handler(request))

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        blocked = self._blocked_repeated_tool_message(request)
        if blocked is not None:
            return blocked
        request = self._with_auto_description(request)
        return self._mark_error_result(await handler(request))

    def _maybe_finalize(self, state: AgentState, runtime: Runtime) -> dict | None:
        del runtime
        messages = list(state.get("messages", []))
        if not messages:
            return None
        last_message = messages[-1]
        if getattr(last_message, "type", None) != "ai":
            return None
        if not getattr(last_message, "tool_calls", None):
            return None

        runtime_state = dict(state.get("runtime") or {})
        if _research_closure_active(runtime_state):
            tool_calls = list(getattr(last_message, "tool_calls", []) or [])
            tool_names = {str(call.get("name") or "") for call in tool_calls if isinstance(call, dict)}
            if tool_names and tool_names <= _WEB_RESEARCH_TOOLS:
                runtime_state["research_closure"]["summary_mode"] = "model_guided"
                runtime_state["research_closure"]["soft_review_tool_calls"] = sorted(tool_names)
                runtime_state["self_feedback_action"] = "self_review_web_tools_after_research_closure"
                return {"runtime": runtime_state}

        error_entries = _tool_error_entries(messages, include_recovery_guards=True)
        if len(error_entries) < self.final_failure_errors:
            return None

        runtime_state = dict(state.get("runtime") or {})
        runtime_state["tool_recovery"] = {
            "stage": "final_soft_review",
            "error_count": len(error_entries),
            "hard_stop": False,
            "action": "let_model_self_iterate_after_repeated_tool_failures",
        }
        return {"runtime": runtime_state}

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_finalize(state, runtime)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_finalize(state, runtime)
