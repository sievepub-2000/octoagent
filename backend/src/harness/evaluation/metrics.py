"""Evaluation metrics for OctoAgent.

Defines quantitative metrics extracted from agent session traces,
mirroring the patterns established in openakita's evaluation system.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceMetrics:
    """Quantitative metrics extracted from a single agent trace (one complete user request)."""

    trace_id: str
    session_id: str = ""
    timestamp: float = field(default_factory=time.time)

    # Volume metrics
    total_iterations: int = 0
    total_llm_calls: int = 0
    total_tool_calls: int = 0
    total_tokens_used: int = 0

    # Latency metrics (seconds)
    total_latency_s: float = 0.0
    first_token_latency_s: float = 0.0
    avg_llm_call_latency_s: float = 0.0

    # Quality metrics (0.0 – 1.0)
    task_success: float | None = None  # 1.0 = success, 0.0 = failure
    tool_success_rate: float | None = None  # fraction of tool calls that did not error
    relevance_score: float | None = None  # LLM-as-judge: answer relevance
    groundedness_score: float | None = None  # LLM-as-judge: factual grounding
    coherence_score: float | None = None  # LLM-as-judge: response coherence

    # Error / cost
    error_count: int = 0
    error_types: list[str] = field(default_factory=list)
    estimated_cost_usd: float = 0.0

    # Metadata
    agent_name: str = ""
    model_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def overall_quality_score(self) -> float | None:
        """Average of available LLM-judge scores (0.0 – 1.0)."""
        scores = [s for s in (self.relevance_score, self.groundedness_score, self.coherence_score) if s is not None]
        if not scores:
            return None
        return sum(scores) / len(scores)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict for JSON/storage."""
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "total_iterations": self.total_iterations,
            "total_llm_calls": self.total_llm_calls,
            "total_tool_calls": self.total_tool_calls,
            "total_tokens_used": self.total_tokens_used,
            "total_latency_s": self.total_latency_s,
            "first_token_latency_s": self.first_token_latency_s,
            "avg_llm_call_latency_s": self.avg_llm_call_latency_s,
            "task_success": self.task_success,
            "tool_success_rate": self.tool_success_rate,
            "relevance_score": self.relevance_score,
            "groundedness_score": self.groundedness_score,
            "coherence_score": self.coherence_score,
            "overall_quality_score": self.overall_quality_score(),
            "error_count": self.error_count,
            "error_types": self.error_types,
            "estimated_cost_usd": self.estimated_cost_usd,
            "agent_name": self.agent_name,
            "model_id": self.model_id,
            "extra": self.extra,
        }


@dataclass
class AggregatedMetrics:
    """Aggregated statistics over a collection of TraceMetrics."""

    sample_count: int = 0
    avg_latency_s: float = 0.0
    p50_latency_s: float = 0.0
    p90_latency_s: float = 0.0
    p95_latency_s: float = 0.0
    p99_latency_s: float = 0.0
    avg_total_iterations: float = 0.0
    avg_llm_calls: float = 0.0
    avg_tool_calls: float = 0.0
    avg_tokens: float = 0.0
    overall_task_success_rate: float | None = None
    avg_overall_quality: float | None = None
    avg_cost_usd: float = 0.0
    error_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "avg_latency_s": self.avg_latency_s,
            "p50_latency_s": self.p50_latency_s,
            "p90_latency_s": self.p90_latency_s,
            "p95_latency_s": self.p95_latency_s,
            "p99_latency_s": self.p99_latency_s,
            "avg_total_iterations": self.avg_total_iterations,
            "avg_llm_calls": self.avg_llm_calls,
            "avg_tool_calls": self.avg_tool_calls,
            "avg_tokens": self.avg_tokens,
            "overall_task_success_rate": self.overall_task_success_rate,
            "avg_overall_quality": self.avg_overall_quality,
            "avg_cost_usd": self.avg_cost_usd,
            "error_rate": self.error_rate,
        }


def aggregate_metrics(traces: list[TraceMetrics]) -> AggregatedMetrics:
    """Compute aggregate statistics from a list of TraceMetrics."""
    if not traces:
        return AggregatedMetrics()

    import statistics

    latencies = sorted(t.total_latency_s for t in traces)
    n = len(latencies)

    def percentile(data: list[float], p: float) -> float:
        idx = round((len(data) - 1) * p / 100)
        return data[idx]

    success_values = [t.task_success for t in traces if t.task_success is not None]
    quality_values = [q for t in traces if (q := t.overall_quality_score()) is not None]
    error_traces = sum(1 for t in traces if t.error_count > 0)

    return AggregatedMetrics(
        sample_count=n,
        avg_latency_s=statistics.mean(latencies),
        p50_latency_s=percentile(latencies, 50),
        p90_latency_s=percentile(latencies, 90),
        p95_latency_s=percentile(latencies, 95),
        p99_latency_s=percentile(latencies, 99),
        avg_total_iterations=statistics.mean(t.total_iterations for t in traces),
        avg_llm_calls=statistics.mean(t.total_llm_calls for t in traces),
        avg_tool_calls=statistics.mean(t.total_tool_calls for t in traces),
        avg_tokens=statistics.mean(t.total_tokens_used for t in traces),
        overall_task_success_rate=statistics.mean(success_values) if success_values else None,
        avg_overall_quality=statistics.mean(quality_values) if quality_values else None,
        avg_cost_usd=statistics.mean(t.estimated_cost_usd for t in traces),
        error_rate=error_traces / n,
    )
