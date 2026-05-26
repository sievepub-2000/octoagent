"""Strategy-pack harmonization for Brain Core module analyses."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import BrainAnalysis, BrainModuleReport


@dataclass(frozen=True)
class StrategyPackSummary:
    """Compact summary after harmonizing module outputs."""

    merged_analysis: BrainAnalysis
    execution_order: list[str]


class BrainStrategyPack:
    """Merge module outputs into one coherent strategy pack."""

    _module_weight = {
        "research": 1.0,
        "evidence_router": 1.2,
        "memory_reasoner": 0.8,
        "quant": 1.1,
    }

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    def merge(self, module_reports: list[BrainModuleReport]) -> StrategyPackSummary:
        execution_order = [report.name for report in module_reports]
        findings = self._dedupe([finding for report in module_reports for finding in report.findings])
        risks = self._dedupe([risk for report in module_reports for risk in report.risks])

        weighted = 0.0
        total_weight = 0.0
        for report in module_reports:
            weight = self._module_weight.get(report.name, 1.0)
            weighted += report.confidence * weight
            total_weight += weight

        base_confidence = (weighted / total_weight) if total_weight else 0.0
        risk_penalty = min(0.35, 0.04 * len(risks))
        confidence = max(0.0, min(1.0, base_confidence - risk_penalty))

        if execution_order:
            findings.insert(
                0,
                "Unified strategy pack: " + " -> ".join(execution_order) + ".",
            )

        return StrategyPackSummary(
            merged_analysis=BrainAnalysis(
                findings=findings,
                risks=risks,
                confidence=confidence,
            ),
            execution_order=execution_order,
        )
