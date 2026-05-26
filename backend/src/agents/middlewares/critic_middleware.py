"""Critic middleware (Sprint-3 P0).

Validates the latest ``AIMessage`` against the active ``goal_contract``:

  * Detects mentions of ``forbidden_actions`` (substring / keyword match).
  * Tracks ``success_criteria`` coverage across the rolling transcript.
  * Surfaces concise feedback as a ``SystemMessage`` (``<critic_feedback>``)
    so the next model turn can self-correct.

The critic is intentionally **lightweight** (no LLM call); Sprint-4 will gate
an LLM-based critic behind a fast model env flag. The current heuristic costs
≪ 1 ms per turn and runs only when a contract is present.
"""

from __future__ import annotations

import logging
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


def _ai_text(messages: list[Any]) -> str:
    """Return concatenated text of all AIMessages (cap 4000 chars)."""
    chunks: list[str] = []
    for msg in messages:
        if getattr(msg, "type", None) != "ai":
            continue
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    chunks.append(str(part.get("text", "")))
        else:
            chunks.append(str(content))
    joined = "\n".join(chunks)
    return joined[-4000:]  # only check the recent tail


def _latest_ai_text(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if getattr(msg, "type", None) != "ai":
            continue
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    return str(part.get("text", ""))
            return ""
        return str(content)
    return ""


class CriticMiddleware(AgentMiddleware[AgentState]):
    """Inject a ``<critic_feedback>`` SystemMessage when violations are detected."""

    def __init__(
        self,
        *,
        every_n: int = 3,
        max_alerts_per_thread: int = 5,
    ):
        super().__init__()
        self.every_n = max(1, every_n)
        self.max_alerts_per_thread = max(1, max_alerts_per_thread)
        self._turn_counter = 0
        self._alerts_sent = 0
        self._last_feedback_signature: str | None = None

    @staticmethod
    def _parse_contract_from_messages(messages: list[Any]) -> dict[str, list[str]] | None:
        """Parse the most recent <goal_contract> block."""
        for msg in reversed(messages):
            content = getattr(msg, "content", "")
            if not isinstance(content, str) or "<goal_contract>" not in content:
                continue
            inside = content.split("<goal_contract>", 1)[1].split("</goal_contract>", 1)[0]
            success: list[str] = []
            forbidden: list[str] = []
            current: list[str] | None = None
            for line in inside.splitlines():
                stripped = line.strip()
                if stripped.startswith("success_criteria:"):
                    current = success
                    continue
                if stripped.startswith("forbidden_actions:"):
                    current = forbidden
                    continue
                if stripped.startswith("must_use_tools:") or stripped.startswith("summary:") or stripped.startswith("issued_at:"):
                    current = None
                    continue
                if stripped.startswith("- ") and current is not None:
                    current.append(stripped[2:].strip())
            if not success and not forbidden:
                return None
            return {"success_criteria": success, "forbidden_actions": forbidden}
        return None

    def _maybe_critique(self, state: AgentState) -> dict | None:
        self._turn_counter += 1
        if self._turn_counter % self.every_n != 0:
            return None
        if self._alerts_sent >= self.max_alerts_per_thread:
            return None
        messages = list(state.get("messages", []) or [])
        contract = self._parse_contract_from_messages(messages)
        if not contract:
            return None
        latest = _latest_ai_text(messages).lower()
        if not latest:
            return None
        full = _ai_text(messages).lower()

        forbidden = contract.get("forbidden_actions") or []
        success = contract.get("success_criteria") or []

        violations: list[str] = []
        for f in forbidden:
            f_clean = str(f).strip().lower()
            if not f_clean:
                continue
            # Heuristic: match the first 4 significant words of the forbidden
            # clause inside the latest AI output.
            head = " ".join(w for w in f_clean.split() if len(w) > 2)[:60]
            if head and head in latest:
                violations.append(f[:120])

        missing: list[str] = []
        for s in success:
            s_clean = str(s).strip().lower()
            if not s_clean:
                continue
            # Skip criteria that are already covered somewhere in the transcript.
            head = " ".join(w for w in s_clean.split() if len(w) > 2)[:60]
            if head and head not in full:
                missing.append(s[:120])

        # Check source attribution completeness
        citation_gap: list[str] = []
        runtime_state = dict(state.get("runtime") or {})
        instruction_contract = runtime_state.get("instruction_contract")
        if isinstance(instruction_contract, dict):
            min_links = instruction_contract.get("min_evidence_links", 0)
            requires_source = instruction_contract.get("requires_tool_evidence", False)
            if requires_source and min_links > 0:
                # Count URLs in the latest AI response
                import re as _re

                url_count = len(_re.findall(r"https?://[^\s\)]+", latest))
                if url_count < min_links:
                    citation_gap.append(f"Response contains {url_count} URLs but instruction contract requires at least {min_links}")

        if not violations and not missing and not citation_gap:
            return None

        parts = ["<critic_feedback>"]
        if violations:
            parts.append(f"  ✗ Forbidden actions mentioned: {'; '.join(violations[:3])}")
        if missing:
            parts.append(f"  ⚠ Success criteria not yet addressed: {'; '.join(missing[:3])}")
        if citation_gap:
            parts.append(f"  ⚠ Citation gap: {'; '.join(citation_gap[:2])}")
        parts.append("  → Re-check the goal contract and adjust the next response.")
        parts.append("</critic_feedback>")

        # Avoid spamming identical feedback turn after turn.
        sig = "|".join(parts[1:-1])
        if sig == self._last_feedback_signature:
            return None
        self._last_feedback_signature = sig
        self._alerts_sent += 1
        logger.info(
            "CriticMiddleware: emitted feedback (turn=%d, violations=%d, missing=%d)",
            self._turn_counter,
            len(violations),
            len(missing),
        )
        return {"messages": [SystemMessage(content="\n".join(parts))]}

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._maybe_critique(state)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        # Pure-python check, no IO — direct call is fine.
        return self._maybe_critique(state)


__all__ = ["CriticMiddleware"]
