"""Merged goal middleware: contract production + drift detection."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
from datetime import UTC, datetime
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from src.models.embedding_service import get_embedding_service
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


_produce_contract = _produce_contract_heuristic


def _produce_contract_llm(text: str) -> GoalContract | None:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from src.models import create_chat_model

        model_name = os.getenv("OCTOAGENT_GOAL_CONTRACT_MODEL") or None
        model = create_chat_model(name=model_name, thinking_enabled=False)
        import json as _json

        prompt = (
            "You extract a structured GoalContract from a user's first message in a "
            "long-running agent thread. Be conservative: only list success_criteria "
            "and forbidden_actions that are explicit in the user message; do NOT "
            "invent constraints. Keep each list item under 160 characters. "
            "If the user did not specify any forbidden_actions or must_use_tools, "
            "return empty lists for those fields. "
            "Reply in the same natural language as the user message.\n\n"
            "User first message:\n```\n{text}\n```"
        ).format(text=text[:4000])
        resp = model.invoke(
            [
                SystemMessage(content=(
                    "Output ONLY a single JSON object, no prose, no markdown fences. Schema: "
                    '{"goal_summary": string, "success_criteria": string[], '
                    '"forbidden_actions": string[], "must_use_tools": string[]}. '
                    "Each list capped at 6 items (8 for tools), each item <= 160 chars. "
                    "Use empty arrays when nothing is explicit in the user message. "
                    "Reply in the same natural language as the user message."
                )),
                HumanMessage(content=prompt),
            ]
        )
        raw = getattr(resp, "content", "") or ""
        if isinstance(raw, list):
            raw = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw)
        s = (raw or "").strip()
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\s*", "", s)
            s = re.sub(r"\s*```\s*$", "", s)
        try:
            data = _json.loads(s)
        except Exception:
            m = re.search(r"\{.*\}", s, re.DOTALL)
            if m:
                try:
                    data = _json.loads(m.group(0))
                except Exception:
                    return None
            else:
                return None
        from pydantic import BaseModel, Field

        class _GCLLMOut(BaseModel):
            goal_summary: str = Field(description="Goal summary")
            success_criteria: list[str] = Field(default_factory=list)
            forbidden_actions: list[str] = Field(default_factory=list)
            must_use_tools: list[str] = Field(default_factory=list)

        out = _GCLLMOut.model_validate(data)
        return GoalContract(
            goal_summary=(out.goal_summary or text.strip()[:200] or "<empty>")[:240],
            success_criteria=[s[:160] for s in (out.success_criteria or [])][:6],
            forbidden_actions=[s[:160] for s in (out.forbidden_actions or [])][:6],
            must_use_tools=[s[:64] for s in (out.must_use_tools or [])][:8],
            issued_at_iso=datetime.now(UTC).isoformat(),
            issued_by_model=f"llm:{model_name or 'default'}",
        )
    except Exception as exc:
        logger.warning("GoalContract LLM producer failed (%s); falling back to heuristic.", exc)
        return None


def _produce_contract_dispatched(text: str) -> GoalContract:
    if _env_truthy("OCTOAGENT_GOAL_CONTRACT_LLM"):
        c = _produce_contract_llm(text)
        if c is not None:
            return c
    return _produce_contract_heuristic(text)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


class GoalMiddleware(AgentMiddleware[AgentState]):
    """Produce GoalContract on first turn (before_model) and detect drift every N turns (after_model)."""

    _seen_first_message_ids: set[str] = set()

    def __init__(
        self,
        *,
        every_n: int = int(os.getenv("OCTO_GOAL_DRIFT_EVERY_N", "3")),
        drift_threshold: float = float(os.getenv("OCTO_GOAL_DRIFT_THRESHOLD", "0.50")),
        window: int = int(os.getenv("OCTO_GOAL_DRIFT_WINDOW", "8")),
    ):
        super().__init__()
        self.every_n = max(1, every_n)
        self.drift_threshold = drift_threshold
        self.window = max(1, window)
        self._turn_counter = 0
        self._goal_emb_cache: tuple[str, list[float]] | None = None

    # ── GoalContract production (before_model) ──

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

    def _render_contract(self, contract: GoalContract) -> str:
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

    def _precheck_contract(self, state: AgentState) -> str | None:
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
        return text

    # ── Goal drift detection (after_model) ──

    def _goal_embedding(self, goal_summary: str) -> list[float] | None:
        if self._goal_emb_cache and self._goal_emb_cache[0] == goal_summary:
            return self._goal_emb_cache[1]
        try:
            emb = get_embedding_service().embed_one(goal_summary)
        except Exception as exc:
            logger.debug("GoalMiddleware: goal-embedding failed: %s", exc)
            return None
        self._goal_emb_cache = (goal_summary, emb)
        return emb

    def _recent_ai_text(self, messages: list[Any]) -> str:
        snippets: list[str] = []
        for msg in reversed(messages):
            if getattr(msg, "type", None) == "ai":
                content = getattr(msg, "content", "")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            snippets.append(str(part.get("text", "")))
                else:
                    snippets.append(str(content))
                if len(snippets) >= self.window:
                    break
        return "\n".join(reversed(snippets))[:2000]

    def _parse_goal_from_messages(self, messages: list[Any]) -> str | None:
        for msg in reversed(messages):
            content = getattr(msg, "content", "")
            if not isinstance(content, str) or "<goal_contract>" not in content:
                continue
            inside = content.split("<goal_contract>", 1)[1].split("</goal_contract>", 1)[0]
            for line in inside.splitlines():
                line = line.strip()
                if line.startswith("summary:"):
                    return line.split("summary:", 1)[1].strip() or None
            return None
        return None

    def _parse_task_state_goal(self, messages: list[Any]) -> str | None:
        for msg in reversed(messages):
            content = getattr(msg, "content", "")
            if not isinstance(content, str):
                continue
            if "[OctoAgent persistent task state]" not in content and "Persistent task state:" not in content:
                continue
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("Goal:"):
                    return stripped.split("Goal:", 1)[1].strip() or None
                if stripped.startswith("- Goal:"):
                    return stripped.split("- Goal:", 1)[1].strip() or None
        return None

    def _active_goal_summary(self, state: AgentState) -> str | None:
        task_state = state.get("task_state")
        if isinstance(task_state, dict):
            status = str(task_state.get("status") or "active").strip().lower()
            goal = str(task_state.get("goal") or "").strip()
            if goal and status not in {"completed", "cancelled", "failed"}:
                return goal
        runtime_state = state.get("runtime") or {}
        if isinstance(runtime_state, dict):
            goal = str(runtime_state.get("task_goal") or runtime_state.get("current_goal") or "").strip()
            if goal:
                return goal
        messages = list(state.get("messages", []) or [])
        return self._parse_task_state_goal(messages) or self._parse_goal_from_messages(messages)

    # ── AgentMiddleware hooks ──

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        text = self._precheck_contract(state)
        if text is None:
            return None
        contract = _produce_contract_dispatched(text)
        logger.info(
            "GoalMiddleware: emitted contract (criteria=%d, forbidden=%d, tools=%d, by=%s)",
            len(contract.success_criteria),
            len(contract.forbidden_actions),
            len(contract.must_use_tools),
            contract.issued_by_model,
        )
        return {"messages": [SystemMessage(content=self._render_contract(contract))]}

    @override
    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        text = self._precheck_contract(state)
        if text is None:
            return None
        contract = await asyncio.to_thread(_produce_contract_dispatched, text)
        return {"messages": [SystemMessage(content=self._render_contract(contract))]}

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        runtime_state = state.get("runtime") or {}
        if isinstance(runtime_state, dict):
            closure = runtime_state.get("research_closure")
            if isinstance(closure, dict) and closure.get("status") == "must_finalize":
                return None
        self._turn_counter += 1
        if self._turn_counter % self.every_n != 0:
            return None
        goal_summary = self._active_goal_summary(state)
        if not goal_summary:
            return None
        messages = state.get("messages", []) or []
        window_text = self._recent_ai_text(list(messages))
        if not window_text:
            return None
        goal_emb = self._goal_embedding(goal_summary)
        if goal_emb is None:
            return None
        try:
            window_emb = get_embedding_service().embed_one(window_text)
        except Exception as exc:
            logger.debug("GoalMiddleware: window-embedding failed: %s", exc)
            return None
        score = _cosine(goal_emb, window_emb)
        logger.debug("GoalMiddleware drift turn=%d score=%.3f thr=%.3f", self._turn_counter, score, self.drift_threshold)
        if score >= self.drift_threshold:
            return None
        alert = SystemMessage(
            content=(
                f"<drift_alert>\n"
                f"  Recent actions diverged from the user goal (cosine={score:.3f} < {self.drift_threshold:.2f}).\n"
                f"  Re-anchor: '{goal_summary[:160]}'\n"
                f"  Re-check success_criteria before continuing.\n"
                f"</drift_alert>"
            )
        )
        logger.warning(
            "GoalMiddleware: drift detected at turn=%d (score=%.3f, threshold=%.2f)",
            self._turn_counter, score, self.drift_threshold,
        )
        return {"messages": [alert]}

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return await asyncio.to_thread(self.after_model, state, runtime)


__all__ = ["GoalMiddleware"]
