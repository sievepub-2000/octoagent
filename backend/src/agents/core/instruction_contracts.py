"""Instruction classification and execution contracts for agent tasks.

The contract is intentionally conservative: it does not execute policy by
itself, but gives the execution loop one stable description of the user's
intent, evidence requirements, and guardrails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

InstructionIntent = Literal[
    "identity",
    "current_research",
    "code_task",
    "system_operation",
    "general",
]
RiskLevel = Literal["low", "medium", "high"]

_IDENTITY_MARKERS = (
    "你是什么模型",
    "什么模型",
    "介绍自己",
    "你是谁",
    "who are you",
    "what model",
    "which model",
)

_CURRENT_RESEARCH_MARKERS = (
    "latest",
    "current",
    "today",
    "recent",
    "news",
    "headlines",
    "trending",
    "search",
    "query",
    "browse",
    "web",
    "最新",
    "当前",
    "实时",
    "新闻",
    "资讯",
    "头条",
    "热点",
    "热榜",
    "查询",
    "检索",
    "搜索",
    "联网",
)

_CODE_TASK_MARKERS = (
    "修复",
    "实现",
    "重构",
    "测试",
    "提交",
    "commit",
    "push",
    "github",
    "代码",
    "仓库",
    "bug",
    "fix",
    "implement",
    "refactor",
)

_SYSTEM_OPERATION_MARKERS = (
    "sudo",
    "提权",
    "免密",
    "删除",
    "清理",
    "rm ",
    "rm -rf",
    "chmod",
    "chown",
    "systemctl",
    "crontab",
    "定时任务",
    "daemon",
    "服务",
)

_DESTRUCTIVE_MARKERS = ("删除", "清理", "rm ", "rm -rf", "wipe", "delete", "remove")
_PRIVILEGE_MARKERS = ("sudo", "提权", "免密", "root", "chmod", "chown")
_PUBLISH_MARKERS = ("push", "推送", "github", "发布", "release", "deploy", "上线")
_DOMAIN_PATTERN = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE)


@dataclass(frozen=True)
class InstructionContract:
    intent: InstructionIntent
    risk_level: RiskLevel = "low"
    requires_tool_evidence: bool = False
    required_tool_categories: tuple[str, ...] = ()
    required_domains: tuple[str, ...] = ()
    min_evidence_links: int = 0
    require_source_attribution: bool = False
    require_runtime_identity: bool = False
    requires_confirmation: bool = False
    guardrails: tuple[str, ...] = ()
    output_requirements: tuple[str, ...] = field(default_factory=tuple)


def _normalize(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _extract_required_domains(text: str) -> tuple[str, ...]:
    domains: list[str] = []
    seen: set[str] = set()
    if "x.com" in text or "twitter" in text or "site:x.com" in text:
        seen.add("x.com")
        domains.append("x.com")
    for match in _DOMAIN_PATTERN.findall(text):
        domain = match.lower()
        if domain == "twitter.com":
            domain = "x.com"
        if domain.startswith("www."):
            domain = domain[4:]
        if domain not in seen:
            seen.add(domain)
            domains.append(domain)
    return tuple(domains)


def _requested_result_count(text: str) -> int:
    if any(marker in text for marker in ("前十", "前10", "十大", "top 10", "top10", "top ten")):
        return 10
    match = re.search(r"(\d{1,2})\s*(?:条|个|items?|results?|links?)", text, re.IGNORECASE)
    if match:
        return max(1, min(int(match.group(1)), 20))
    return 3


def detect_instruction_contract(
    instruction: str | None,
    *,
    metadata: dict[str, Any] | None = None,
) -> InstructionContract:
    """Classify a user instruction into execution requirements."""

    text = _normalize(instruction)
    metadata = metadata or {}
    guardrails: list[str] = []

    is_identity = _contains_any(text, _IDENTITY_MARKERS)
    is_current_research = _contains_any(text, _CURRENT_RESEARCH_MARKERS)
    is_code_task = _contains_any(text, _CODE_TASK_MARKERS)
    is_system_operation = _contains_any(text, _SYSTEM_OPERATION_MARKERS)

    if is_identity and not is_current_research:
        return InstructionContract(
            intent="identity",
            require_runtime_identity=True,
            output_requirements=(
                "Distinguish OctoAgent as the platform/assistant from the active runtime model.",
                "Use runtime telemetry when available; say unknown instead of guessing.",
            ),
        )

    if _contains_any(text, _DESTRUCTIVE_MARKERS):
        guardrails.append("destructive_file_operation")
    if _contains_any(text, _PRIVILEGE_MARKERS):
        guardrails.append("privilege_escalation")
    if _contains_any(text, _PUBLISH_MARKERS):
        guardrails.append("remote_publish")

    if is_system_operation:
        risk_level: RiskLevel = "high" if guardrails else "medium"
        return InstructionContract(
            intent="system_operation",
            risk_level=risk_level,
            requires_confirmation=bool(guardrails),
            guardrails=tuple(dict.fromkeys(guardrails)),
            output_requirements=(
                "Record the exact commands and affected paths before execution.",
                "Verify results with non-destructive inspection after execution.",
            ),
        )

    if is_current_research:
        domains = _extract_required_domains(text)
        min_links = _requested_result_count(text)
        return InstructionContract(
            intent="current_research",
            risk_level="medium",
            requires_tool_evidence=True,
            required_tool_categories=("web",),
            required_domains=domains,
            min_evidence_links=min_links,
            require_source_attribution=True,
            output_requirements=(
                "Use tool-backed evidence for current or time-sensitive claims.",
                "Return source URLs for the concrete content pages that support the answer.",
                "Do not claim completion if the requested pages cannot be fetched or verified.",
                "Cross-validate dynamic data (Stars, prices, rankings) with the actual tool output — never cite stale training data.",
                "Each factual claim in the response must be traceable to a specific tool output.",
                "Before submitting, verify all URLs are correct and all data attributions match their sources.",
            ),
        )

    if is_code_task:
        return InstructionContract(
            intent="code_task",
            risk_level="medium",
            required_tool_categories=("filesystem", "tests"),
            output_requirements=(
                "Inspect relevant files before editing.",
                "Run focused verification after changes and report exact command results.",
                "Never report success without observed evidence from tool output.",
                "If verification fails, analyze the failure and retry with a different approach before reporting to user.",
            ),
        )

    if bool(metadata.get("tool_research")):
        return InstructionContract(
            intent="current_research",
            risk_level="medium",
            requires_tool_evidence=True,
            required_tool_categories=("web",),
            min_evidence_links=3,
            require_source_attribution=True,
            output_requirements=(
                "Use tool-backed evidence for current or time-sensitive claims.",
                "Return source URLs for the concrete content pages that support the answer.",
            ),
        )

    return InstructionContract(intent="general")


def build_contract_prompt(contract: InstructionContract) -> str:
    """Render contract rules as a compact prompt block for the agent loop."""

    lines = [
        "## Instruction contract",
        f"- Intent: {contract.intent}",
        f"- Risk level: {contract.risk_level}",
    ]
    if contract.requires_tool_evidence:
        lines.append("- Requires tool-backed evidence before final answer.")
    if contract.required_tool_categories:
        lines.append("- Required tool categories: " + ", ".join(contract.required_tool_categories))
    if contract.required_domains:
        lines.append("- Required source domains: " + ", ".join(contract.required_domains))
    if contract.min_evidence_links:
        lines.append(f"- Minimum source URLs/content pages: {contract.min_evidence_links}")
    if contract.require_runtime_identity:
        lines.append("- Runtime identity must come from observable runtime/model state; do not guess.")
    if contract.requires_confirmation:
        lines.append("- Requires operator confirmation before dangerous or irreversible actions.")
    if contract.guardrails:
        lines.append("- Guardrails: " + ", ".join(contract.guardrails))
    for requirement in contract.output_requirements:
        lines.append(f"- {requirement}")
    if contract.requires_tool_evidence:
        lines.append("- Do not claim completion without source URLs and captured evidence.")
    return "\n".join(lines)


__all__ = [
    "InstructionContract",
    "build_contract_prompt",
    "detect_instruction_contract",
]
