"""Quant scoping module for the Brain Core skeleton."""

from __future__ import annotations

from .contracts import BrainAnalysis, BrainTaskContext


class BrainQuantEngine:
    """Produce lightweight quant-readiness analysis from normalized task input."""

    name = "quant"
    description = "Evaluate factor, guardrail, and evidence readiness for quant workflows."
    supported_modes = ("plan", "quant")

    def supports(self, context: BrainTaskContext) -> bool:
        return context.preferred_mode in {"plan", "quant"}

    def analyze(self, context: BrainTaskContext) -> BrainAnalysis:
        findings: list[str] = []
        risks: list[str] = []
        confidence = 0.2

        if context.preferred_mode == "quant":
            findings.append("Quant execution path requested explicitly.")
            confidence += 0.1
        else:
            findings.append(
                f"Quant scope evaluated as supporting context for mode: {context.preferred_mode}."
            )

        if context.factor_candidates:
            findings.append(
                "Factor candidates ready for triage: "
                + ", ".join(context.factor_candidates[:5])
            )
            confidence += 0.2
        else:
            risks.append("No factor candidates declared for quant scoring.")

        if context.risk_limits:
            findings.append(
                "Risk limits declared: " + ", ".join(context.risk_limits[:4])
            )
            confidence += 0.15
        else:
            risks.append("No explicit risk limits supplied for quant execution.")

        if context.evidence:
            findings.append(
                f"Evidence can support backtest framing across {len(context.evidence)} item(s)."
            )
            confidence += 0.15
        else:
            risks.append("No evidence supplied for quant validation or backtest selection.")

        if context.constraints:
            findings.append(
                "Execution constraints available for quant gating: "
                + ", ".join(context.constraints[:4])
            )
            confidence += 0.05

        findings.append(
            "Next quant implementation target should connect factor triage, backtest orchestration, and risk-budget enforcement."
        )

        return BrainAnalysis(
            findings=findings,
            risks=risks,
            confidence=min(confidence, 0.85),
        )
