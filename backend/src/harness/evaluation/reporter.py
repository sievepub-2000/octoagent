"""Evaluation report generation for OctoAgent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .runner import EvalJobResult


def generate_json_report(result: EvalJobResult, output_path: str | Path | None = None) -> dict[str, Any]:
    """Generate a JSON evaluation report.

    Args:
        result: The evaluation job result.
        output_path: Optional path to write the report. If None, only returns the dict.

    Returns:
        The report as a Python dict.
    """
    report = result.to_dict()

    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return report


def generate_text_report(result: EvalJobResult) -> str:
    """Generate a human-readable text summary of an evaluation job."""
    lines = [
        f"# Evaluation Report: {result.job_name}",
        f"Job ID: {result.job_id}",
        f"Duration: {result.completed_at - result.started_at:.2f}s",
        f"Samples: {result.successful_samples}/{result.total_samples} successful",
        "",
        "## Scores",
    ]

    if result.avg_relevance is not None:
        lines.append(f"  Relevance:     {result.avg_relevance:.3f}")
    if result.avg_groundedness is not None:
        lines.append(f"  Groundedness:  {result.avg_groundedness:.3f}")
    if result.avg_coherence is not None:
        lines.append(f"  Coherence:     {result.avg_coherence:.3f}")
    if result.avg_overall is not None:
        lines.append(f"  Overall:       {result.avg_overall:.3f}")

    if result.aggregated:
        agg = result.aggregated
        lines.extend(
            [
                "",
                "## Performance",
                f"  Avg latency:   {agg.avg_latency_s:.3f}s",
                f"  P95 latency:   {agg.p95_latency_s:.3f}s",
                f"  Error rate:    {agg.error_rate:.1%}",
            ]
        )

    if result.failed_samples > 0:
        lines.extend(
            [
                "",
                f"## Failures ({result.failed_samples})",
            ]
        )
        for sr in result.sample_results:
            if sr.error:
                lines.append(f"  [{sr.sample_id}] {sr.error}")

    return "\n".join(lines)
