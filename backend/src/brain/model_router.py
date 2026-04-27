"""Model selection routing for the Brain Core.

Maps task characteristics (complexity, risk, mode) to optimal model
provider recommendations so the execution layer can pick the best
available LLM for each job.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from .contracts import BrainAnalysis, BrainDecision, BrainTaskContext

logger = logging.getLogger(__name__)


class ModelRecommendation(BaseModel):
    """Recommended model tier and rationale for a given task."""

    tier: Literal["heavy", "standard", "light"] = "standard"
    reason: str = ""
    suggested_capabilities: list[str] = Field(default_factory=list)
    fallback_tier: Literal["heavy", "standard", "light"] = "standard"


class BrainModelRouter:
    """Select the appropriate model tier based on task context and analysis."""

    # Threshold configuration --------------------------------------------------
    HIGH_RISK_COUNT = 3
    LOW_CONFIDENCE = 0.5
    HIGH_CONFIDENCE = 0.75

    def route(
        self,
        context: BrainTaskContext,
        analysis: BrainAnalysis,
        decision: BrainDecision,
    ) -> ModelRecommendation:
        """Return a model recommendation given the brain's outputs."""

        # High-risk / high-complexity → strongest model
        if decision.risk_level == "high" or len(analysis.risks) >= self.HIGH_RISK_COUNT:
            return ModelRecommendation(
                tier="heavy",
                reason="High-risk task requires strongest reasoning model.",
                suggested_capabilities=["long_context", "tool_use", "reasoning"],
                fallback_tier="standard",
            )

        # Quant mode always needs strong reasoning + code
        if context.preferred_mode == "quant":
            return ModelRecommendation(
                tier="heavy",
                reason="Quant mode requires strong numerical reasoning.",
                suggested_capabilities=["code_generation", "reasoning", "tool_use"],
                fallback_tier="standard",
            )

        # Research mode needs long context
        if context.preferred_mode == "research":
            return ModelRecommendation(
                tier="standard",
                reason="Research mode benefits from balanced context and speed.",
                suggested_capabilities=["long_context", "reasoning"],
                fallback_tier="light",
            )

        # Low confidence → standard model for safety
        if analysis.confidence < self.LOW_CONFIDENCE:
            return ModelRecommendation(
                tier="standard",
                reason=f"Confidence is low ({analysis.confidence:.2f}), using standard model.",
                suggested_capabilities=["reasoning", "tool_use"],
                fallback_tier="heavy",
            )

        # Simple, high-confidence plan → light model is fine
        if (
            analysis.confidence >= self.HIGH_CONFIDENCE
            and not analysis.risks
            and context.preferred_mode == "plan"
        ):
            return ModelRecommendation(
                tier="light",
                reason="High-confidence simple plan can use lightweight model.",
                suggested_capabilities=["tool_use"],
                fallback_tier="standard",
            )

        # Default: standard tier
        return ModelRecommendation(
            tier="standard",
            reason="Default routing to standard model tier.",
            suggested_capabilities=["reasoning", "tool_use"],
            fallback_tier="light",
        )


# ---------------------------------------------------------------------------
# Bridge: ModelRecommendation → create_chat_model()
# ---------------------------------------------------------------------------


def resolve_model_from_recommendation(recommendation: ModelRecommendation):
    """Create a LangChain chat model matching the Brain's recommendation.

    Maps the abstract *tier* and *suggested_capabilities* fields to the
    concrete ``create_chat_model()`` parameters defined in ``src.models``.

    Returns:
        A ``BaseChatModel`` instance selected according to the tier.
    """
    from src.models import create_chat_model

    thinking = "reasoning" in recommendation.suggested_capabilities
    min_ctx = 32_000 if "long_context" in recommendation.suggested_capabilities else None

    try:
        return create_chat_model(
            selection_profile=recommendation.tier,
            thinking_enabled=thinking,
            min_context_tokens=min_ctx,
        )
    except Exception:
        logger.warning(
            "Failed to resolve model for tier '%s', falling back to '%s'",
            recommendation.tier,
            recommendation.fallback_tier,
        )
        return create_chat_model(
            selection_profile=recommendation.fallback_tier,
            thinking_enabled=thinking,
            min_context_tokens=min_ctx,
        )
