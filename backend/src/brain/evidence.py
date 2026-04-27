"""Evidence routing and sufficiency analysis for Brain Core."""

from __future__ import annotations

from .contracts import BrainAnalysis, BrainTaskContext


class BrainEvidenceRouter:
    """Assess whether evidence is concrete enough for downstream execution."""

    name = "evidence_router"
    description = "Normalize evidence sufficiency and execution-readiness signals."
    supported_modes = ("plan", "research", "quant", "policy")

    def supports(self, context: BrainTaskContext) -> bool:
        return True

    def analyze(self, context: BrainTaskContext) -> BrainAnalysis:
        findings: list[str] = []
        risks: list[str] = []
        confidence = 0.15

        if context.evidence:
            findings.append(
                f"Evidence router accepted {len(context.evidence)} evidence item(s) for downstream planning."
            )
            confidence += 0.2
        else:
            risks.append("Evidence router could not validate execution readiness without evidence.")

        if context.constraints:
            findings.append(
                f"Constraint snapshot available for routing: {len(context.constraints)} item(s)."
            )
            confidence += 0.05

        if context.preferred_mode == "research" and not context.evidence:
            risks.append("Research mode requires evidence before synthesis can be trusted.")

        return BrainAnalysis(
            findings=findings,
            risks=risks,
            confidence=min(confidence, 0.55),
        )
