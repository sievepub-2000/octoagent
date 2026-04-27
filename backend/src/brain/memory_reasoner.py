"""Memory-hint reasoning module for Brain Core."""

from __future__ import annotations

from .contracts import BrainAnalysis, BrainTaskContext


class BrainMemoryReasoner:
    """Translate memory hints into execution context without mutating memory state."""

    name = "memory_reasoner"
    description = "Lift memory hints into reusable planning context."
    supported_modes = ("plan", "research", "quant", "policy")

    def supports(self, context: BrainTaskContext) -> bool:
        return True

    def analyze(self, context: BrainTaskContext) -> BrainAnalysis:
        findings: list[str] = []
        risks: list[str] = []
        confidence = 0.1

        if context.memory_hints:
            findings.append(
                "Memory hints available for plan shaping: "
                + ", ".join(context.memory_hints[:5])
            )
            confidence += 0.2
        else:
            findings.append("No memory hints supplied; planner will stay goal-local.")

        if context.preferred_mode in {"research", "policy"} and not context.memory_hints:
            risks.append(
                "Cross-session memory hints are absent for a mode that benefits from prior context."
            )

        return BrainAnalysis(
            findings=findings,
            risks=risks,
            confidence=min(confidence, 0.4),
        )
