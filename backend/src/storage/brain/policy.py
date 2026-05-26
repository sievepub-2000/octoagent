"""Policy layer for the Brain Core skeleton."""

from __future__ import annotations

from .contracts import BrainAnalysis, BrainDecision, BrainTaskContext


class BrainPolicy:
    """Translate analysis into a conservative recommendation."""

    def decide(self, context: BrainTaskContext, analysis: BrainAnalysis) -> BrainDecision:
        if len(analysis.risks) >= 3:
            return BrainDecision(
                recommendation=f"Delay autonomous execution for: {context.user_goal}",
                rationale=analysis.risks[:5],
                risk_level="high",
            )

        if analysis.risks:
            return BrainDecision(
                recommendation=f"Require manual review before execution for: {context.user_goal}",
                rationale=analysis.risks[:4] + analysis.findings[:2],
                risk_level="medium",
            )

        if analysis.confidence < 0.5:
            return BrainDecision(
                recommendation=f"Require manual review before execution for: {context.user_goal}",
                rationale=[
                    f"Confidence remains low at {analysis.confidence:.2f}.",
                    *analysis.findings[:3],
                ],
                risk_level="medium",
            )

        if context.preferred_mode == "quant" and context.factor_candidates and context.risk_limits:
            return BrainDecision(
                recommendation=f"Proceed with bounded quant exploration for: {context.user_goal}",
                rationale=[
                    "Quant scope includes factors and explicit risk limits.",
                    *analysis.findings[:4],
                ],
                risk_level="medium",
            )

        return BrainDecision(
            recommendation=f"Proceed with controlled execution for: {context.user_goal}",
            rationale=analysis.findings[:5],
            risk_level="low" if analysis.confidence >= 0.75 else "medium",
        )
