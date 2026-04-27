"""Research module for the Brain Core skeleton."""

from __future__ import annotations

from .contracts import BrainAnalysis, BrainTaskContext


class BrainResearcher:
    """Produce lightweight evidence and risk framing."""

    name = "research"
    description = "Generate baseline goal, evidence, and constraint framing."
    supported_modes = ("plan", "research", "quant", "policy")

    def supports(self, context: BrainTaskContext) -> bool:
        return True

    def analyze(self, context: BrainTaskContext) -> BrainAnalysis:
        findings = [
            f"Primary goal recognized: {context.user_goal}",
            f"Constraint count: {len(context.constraints)}",
            f"Evidence items available: {len(context.evidence)}",
        ]
        if context.factor_candidates:
            findings.append(f"Factor candidates: {', '.join(context.factor_candidates[:5])}")
        if context.memory_hints:
            findings.append(f"Memory hints available: {len(context.memory_hints)}")
        risks = ["Insufficient domain-specific evidence"] if not context.evidence else []
        if context.risk_limits:
            findings.append(f"Risk limits declared: {len(context.risk_limits)}")
        confidence = 0.35 if not context.evidence else 0.65
        return BrainAnalysis(findings=findings, risks=risks, confidence=confidence)
