"""GoalContract producer middleware (Sprint-4 LLM upgrade).

Runs once at the start of a new thread to derive a ``GoalContract`` from the
first user message and inject it as a SystemMessage into the model stream.

Two producers:
  * regex-heuristic (default; zero-latency, zero-cost)
  * LLM-based (gated by env ``OCTOAGENT_GOAL_CONTRACT_LLM=1``; falls back to
    heuristic on any failure)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from src.storage.brain.goal_contract import GoalContract

logger = logging.getLogger(__name__)

_SUCCESS_HINTS = ("ensure", "must", "should", "需要", "必须", "确保", "完成", "validate", "verify")
_FORBIDDEN_HINTS = ("don't", "do not", "never", "不要", "禁止", "不能")
_TOOL_MENTION_RE = re.compile(r"`([a-z_][a-z0-9_]+)`", re.IGNORECASE)


def _split_clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r"[;\n。.!?]+", text) if c.strip()]


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _produce_contract_heuristic(text: str) -> GoalContract:
    summary = text.strip()[:200] or "<empty>"
    success: list[str] = []
    forbidden: list[str] = []
    for clause in _split_clauses(text):
        low = clause.lower()
        if any(h in low for h in _FORBIDDEN_HINTS):
            forbidden.append(clause[:160])
        elif any(h in low for h in _SUCCESS_HINTS):
            success.append(clause[:160])
    tools = sorted(set(_TOOL_MENTION_RE.findall(text)))[:8]
    return GoalContract(
        goal_summary=summary,
        success_criteria=success[:6],
        forbidden_actions=forbidden[:6],
        must_use_tools=tools,
        issued_at_iso=datetime.now(UTC).isoformat(),
        issued_by_model="heuristic",
    )


# Backward-compatible alias for any external callers/tests.
_produce_contract = _produce_contract_heuristic


class _GoalContractLLMOutput(BaseModel):
    """Pydantic schema for structured LLM extraction."""

    goal_summary: str = Field(description="One-sentence restatement of the user's intent in the same language as the user.")
    success_criteria: list[str] = Field(default_factory=list, description="Concrete, verifiable conditions that mark the task as complete. Max 6 items.")
    forbidden_actions: list[str] = Field(default_factory=list, description="Things the agent must NOT do while solving this task. Max 6 items.")
    must_use_tools: list[str] = Field(default_factory=list, description="Tool names that the user explicitly asked the agent to use. Max 8 items. Empty if none mentioned.")


_LLM_PROMPT = (
    "You extract a structured GoalContract from a user's first message in a "
    "long-running agent thread. Be conservative: only list success_criteria "
    "and forbidden_actions that are explicit in the user message; do NOT "
    "invent constraints. Keep each list item under 160 characters. "
    "If the user did not specify any forbidden_actions or must_use_tools, "
    "return empty lists for those fields. "
    "Reply in the same natural language as the user message.\n\n"
    "User first message:\n```\n{text}\n```"
)


_LLM_JSON_INSTRUCTION = (
    "Output ONLY a single JSON object, no prose, no markdown fences. Schema: "
    '{"goal_summary": string, "success_criteria": string[], '
    '"forbidden_actions": string[], "must_use_tools": string[]}. '
    "Each list capped at 6 items (8 for tools), each item <= 160 chars. "
    "Use empty arrays when nothing is explicit in the user message. "
    "Reply in the same natural language as the user message."
)


def _parse_llm_json(raw: str) -> dict | None:
    import json as _json

    s = (raw or "").strip()
    # Strip fenced code blocks if model added them.
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    # Try strict parse, then locate first {...} block.
    try:
        return _json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if not m:
            return None
        try:
            return _json.loads(m.group(0))
        except Exception:
            return None


def _produce_contract_llm(text: str) -> GoalContract | None:
    """Use the configured chat model to produce a structured GoalContract.

    Returns ``None`` if the LLM is unavailable or the call fails.
    """
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from src.models import create_chat_model

        model_name = os.getenv("OCTOAGENT_GOAL_CONTRACT_MODEL") or None
        model = create_chat_model(name=model_name, thinking_enabled=False)
        prompt = _LLM_PROMPT.format(text=text[:4000])
        resp = model.invoke(
            [
                SystemMessage(content=_LLM_JSON_INSTRUCTION),
                HumanMessage(content=prompt),
            ]
        )
        raw = getattr(resp, "content", "") or ""
        if isinstance(raw, list):
            # Collapse list-of-parts content into a single string.
            raw = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw)
        data = _parse_llm_json(raw)
        if not isinstance(data, dict):
            logger.warning("GoalContractProducer: LLM output not parseable as JSON; raw=%r", raw[:200])
            return None
        try:
            out = _GoalContractLLMOutput.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GoalContractProducer: LLM JSON failed schema validation (%s)", exc)
            return None
        return GoalContract(
            goal_summary=(out.goal_summary or text.strip()[:200] or "<empty>")[:240],
            success_criteria=[s[:160] for s in (out.success_criteria or [])][:6],
            forbidden_actions=[s[:160] for s in (out.forbidden_actions or [])][:6],
            must_use_tools=[s[:64] for s in (out.must_use_tools or [])][:8],
            issued_at_iso=datetime.now(UTC).isoformat(),
            issued_by_model=f"llm:{model_name or 'default'}",
        )
    except Exception as exc:  # noqa: BLE001 - intentional broad guard
        logger.warning("GoalContractProducer: LLM producer failed (%s); falling back to heuristic.", exc)
        return None


def _produce_contract_dispatched(text: str) -> GoalContract:
    if _env_truthy("OCTOAGENT_GOAL_CONTRACT_LLM"):
        contract = _produce_contract_llm(text)
        if contract is not None:
            return contract
    return _produce_contract_heuristic(text)


class GoalContractProducerMiddleware(AgentMiddleware[AgentState]):
    """Stash a ``GoalContract`` into state on the first turn."""

    @staticmethod
    def _extract_first_user_text(messages: list[Any]) -> str | None:
        for msg in messages:
            if getattr(msg, "type", None) in {"human", "user"}:
                c = getattr(msg, "content", "")
                if isinstance(c, list):
                    for part in c:
                        if isinstance(part, dict) and part.get("type") == "text":
                            return part.get("text") or None
                    return None
                return str(c) or None
        return None

    # Per-thread cache so we do not re-emit when LangGraph replays the same
    # before_model phase across run attempts. Keyed by id() of the user
    # message which is stable within a thread.
    _seen_first_message_ids: set[str] = set()

    @staticmethod
    def _render_block(contract: GoalContract) -> str:
        lines = ["<goal_contract>"]
        lines.append(f"  summary: {contract.goal_summary}")
        if contract.success_criteria:
            lines.append("  success_criteria:")
            for s in contract.success_criteria:
                lines.append(f"    - {s}")
        if contract.forbidden_actions:
            lines.append("  forbidden_actions:")
            for f in contract.forbidden_actions:
                lines.append(f"    - {f}")
        if contract.must_use_tools:
            lines.append(f"  must_use_tools: {', '.join(contract.must_use_tools)}")
        if contract.issued_by_model:
            lines.append(f"  issued_by: {contract.issued_by_model}")
        lines.append(f"  issued_at: {contract.issued_at_iso}")
        lines.append("</goal_contract>")
        return "\n".join(lines)

    def _precheck(self, state: AgentState) -> tuple[str, str] | None:
        """Return ``(text, first_id)`` if a contract should be produced, else None."""
        messages = list(state.get("messages", []) or [])
        for m in messages:
            content = getattr(m, "content", "")
            if isinstance(content, str) and "<goal_contract>" in content:
                return None
        text = self._extract_first_user_text(messages)
        if not text:
            return None
        first_id = None
        for m in messages:
            if getattr(m, "type", None) in {"human", "user"}:
                first_id = str(getattr(m, "id", "")) or None
                break
        if first_id and first_id in self._seen_first_message_ids:
            return None
        if first_id:
            self._seen_first_message_ids.add(first_id)
        return (text, first_id or "")

    def _emit(self, contract: GoalContract) -> dict:
        logger.info(
            "GoalContractProducer: emitted contract (criteria=%d, forbidden=%d, tools=%d, by=%s)",
            len(contract.success_criteria),
            len(contract.forbidden_actions),
            len(contract.must_use_tools),
            contract.issued_by_model,
        )
        from langchain_core.messages import SystemMessage

        return {"messages": [SystemMessage(content=self._render_block(contract))]}

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        pre = self._precheck(state)
        if pre is None:
            return None
        text, _ = pre
        contract = _produce_contract_dispatched(text)
        return self._emit(contract)

    @override
    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        pre = self._precheck(state)
        if pre is None:
            return None
        text, _ = pre
        # LLM path (if gated) may do blocking network I/O; run in a thread.
        contract = await asyncio.to_thread(_produce_contract_dispatched, text)
        return self._emit(contract)


__all__ = ["GoalContractProducerMiddleware"]
