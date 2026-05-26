"""LLM-as-Judge evaluation for OctoAgent.

Scores agent responses along three dimensions:
- Relevance: Does the answer address the question?
- Groundedness: Is the answer factually supported?
- Coherence: Is the answer logically consistent and well-structured?

Each dimension returns a float in [0.0, 1.0].
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Prompt templates for LLM judge scoring
_RELEVANCE_PROMPT = """\
You are an expert evaluator. Score the following answer's relevance to the question on a scale from 0 to 1.
- 1.0: The answer fully and directly addresses the question.
- 0.5: The answer partially addresses the question.
- 0.0: The answer does not address the question at all.

Question: {question}
Answer: {answer}

Respond ONLY with a JSON object: {{"score": <float 0.0-1.0>, "reason": "<brief reason>"}}"""

_GROUNDEDNESS_PROMPT = """\
You are an expert evaluator. Score how well the following answer is grounded in verifiable facts on a scale from 0 to 1.
- 1.0: All claims are factually accurate and verifiable.
- 0.5: Some claims are accurate; others are uncertain or unverifiable.
- 0.0: Claims are incorrect or fabricated.

Answer: {answer}
Context (if available): {context}

Respond ONLY with a JSON object: {{"score": <float 0.0-1.0>, "reason": "<brief reason>"}}"""

_COHERENCE_PROMPT = """\
You are an expert evaluator. Score the coherence of the following answer on a scale from 0 to 1.
- 1.0: The answer is logically consistent, well-structured, and easy to follow.
- 0.5: The answer has some structure but contains repetition or unclear parts.
- 0.0: The answer is incoherent or self-contradictory.

Answer: {answer}

Respond ONLY with a JSON object: {{"score": <float 0.0-1.0>, "reason": "<brief reason>"}}"""


@dataclass
class JudgeScore:
    """Result of a single LLM judge evaluation."""

    dimension: str
    score: float
    reason: str
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "score": self.score,
            "reason": self.reason,
        }


@dataclass
class JudgeResult:
    """Complete judge evaluation result for a single response."""

    question: str
    answer: str
    relevance: JudgeScore | None = None
    groundedness: JudgeScore | None = None
    coherence: JudgeScore | None = None
    error: str | None = None

    @property
    def overall_score(self) -> float | None:
        scores = [s.score for s in (self.relevance, self.groundedness, self.coherence) if s is not None]
        return sum(scores) / len(scores) if scores else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "relevance": self.relevance.to_dict() if self.relevance else None,
            "groundedness": self.groundedness.to_dict() if self.groundedness else None,
            "coherence": self.coherence.to_dict() if self.coherence else None,
            "overall_score": self.overall_score,
            "error": self.error,
        }


def _extract_score(raw: str, dimension: str) -> tuple[float, str]:
    """Parse score and reason from LLM judge response."""
    raw = raw.strip()
    # Try JSON parse
    try:
        # Extract JSON block if surrounded by extra text
        match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            score = float(data.get("score", 0.0))
            score = max(0.0, min(1.0, score))
            reason = str(data.get("reason", ""))
            return score, reason
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Fallback: extract bare float
    match = re.search(r"(\d+(?:\.\d+)?)", raw)
    if match:
        score = float(match.group(1))
        if score > 1.0:
            score = score / 10.0
        score = max(0.0, min(1.0, score))
        return score, raw[:200]

    logger.warning(f"Could not parse {dimension} score from: {raw[:100]}")
    return 0.5, "parse_error"


class LLMJudge:
    """Evaluates agent responses using LLM-as-Judge methodology.

    Usage:
        judge = LLMJudge(llm_callable=my_llm_fn)
        result = await judge.evaluate(question="...", answer="...")
    """

    def __init__(self, llm_callable: Any | None = None) -> None:
        """
        Args:
            llm_callable: An async callable (prompt: str) -> str.
                          If None, placeholder scores (0.5) are returned for
                          offline / unit-test usage.
        """
        self._llm = llm_callable

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM and return raw text output."""
        if self._llm is None:
            # Stub for offline / test mode
            return '{"score": 0.5, "reason": "stub_no_llm"}'
        try:
            result = await self._llm(prompt)
            return str(result)
        except Exception as exc:
            logger.error(f"LLM judge call failed: {exc}")
            return '{"score": 0.5, "reason": "llm_error"}'

    async def score_relevance(self, question: str, answer: str) -> JudgeScore:
        prompt = _RELEVANCE_PROMPT.format(question=question, answer=answer)
        raw = await self._call_llm(prompt)
        score, reason = _extract_score(raw, "relevance")
        return JudgeScore(dimension="relevance", score=score, reason=reason, raw_response=raw)

    async def score_groundedness(self, answer: str, context: str = "") -> JudgeScore:
        prompt = _GROUNDEDNESS_PROMPT.format(answer=answer, context=context or "N/A")
        raw = await self._call_llm(prompt)
        score, reason = _extract_score(raw, "groundedness")
        return JudgeScore(dimension="groundedness", score=score, reason=reason, raw_response=raw)

    async def score_coherence(self, answer: str) -> JudgeScore:
        prompt = _COHERENCE_PROMPT.format(answer=answer)
        raw = await self._call_llm(prompt)
        score, reason = _extract_score(raw, "coherence")
        return JudgeScore(dimension="coherence", score=score, reason=reason, raw_response=raw)

    async def evaluate(
        self,
        question: str,
        answer: str,
        context: str = "",
        dimensions: list[str] | None = None,
    ) -> JudgeResult:
        """Run a full 3-dimension evaluation.

        Args:
            question: The user's original question.
            answer: The agent's response to evaluate.
            context: Optional grounding context (retrieved documents, etc.).
            dimensions: Subset of ['relevance','groundedness','coherence'].
                        Default: all three.

        Returns:
            JudgeResult with populated score fields.
        """
        if dimensions is None:
            dimensions = ["relevance", "groundedness", "coherence"]

        result = JudgeResult(question=question, answer=answer)

        try:
            if "relevance" in dimensions:
                result.relevance = await self.score_relevance(question, answer)
            if "groundedness" in dimensions:
                result.groundedness = await self.score_groundedness(answer, context)
            if "coherence" in dimensions:
                result.coherence = await self.score_coherence(answer)
        except Exception as exc:
            result.error = str(exc)
            logger.error(f"Judge evaluation failed: {exc}")

        return result
