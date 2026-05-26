"""Evaluation runner for OctoAgent.

Executes evaluation jobs over datasets of (question, answer) pairs or
by replaying stored session traces.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .judge import JudgeResult, LLMJudge
from .metrics import AggregatedMetrics, TraceMetrics, aggregate_metrics

logger = logging.getLogger(__name__)


@dataclass
class EvalSample:
    """A single evaluation sample."""

    sample_id: str
    question: str
    answer: str
    context: str = ""
    ground_truth: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalJobConfig:
    """Configuration for an evaluation job."""

    job_id: str
    name: str
    samples: list[EvalSample]
    dimensions: list[str] = field(default_factory=lambda: ["relevance", "groundedness", "coherence"])
    max_concurrency: int = 3
    timeout_per_sample_s: float = 30.0
    agent_name: str = ""
    model_id: str = ""


@dataclass
class SampleResult:
    """Result of evaluating a single sample."""

    sample_id: str
    judge_result: JudgeResult
    trace_metrics: TraceMetrics | None = None
    error: str | None = None
    duration_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "judge_result": self.judge_result.to_dict(),
            "trace_metrics": self.trace_metrics.to_dict() if self.trace_metrics else None,
            "error": self.error,
            "duration_s": self.duration_s,
        }


@dataclass
class EvalJobResult:
    """Aggregated result of an evaluation job."""

    job_id: str
    job_name: str
    started_at: float
    completed_at: float
    total_samples: int
    successful_samples: int
    failed_samples: int
    sample_results: list[SampleResult]
    aggregated: AggregatedMetrics | None = None
    avg_relevance: float | None = None
    avg_groundedness: float | None = None
    avg_coherence: float | None = None
    avg_overall: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_name": self.job_name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_s": self.completed_at - self.started_at,
            "total_samples": self.total_samples,
            "successful_samples": self.successful_samples,
            "failed_samples": self.failed_samples,
            "avg_relevance": self.avg_relevance,
            "avg_groundedness": self.avg_groundedness,
            "avg_coherence": self.avg_coherence,
            "avg_overall": self.avg_overall,
            "aggregated_metrics": self.aggregated.to_dict() if self.aggregated else None,
            "sample_results": [r.to_dict() for r in self.sample_results],
        }


class EvaluationRunner:
    """Runs evaluation jobs over datasets using LLM-as-Judge.

    Usage:
        runner = EvaluationRunner(judge=LLMJudge())
        result = await runner.run(config)
    """

    def __init__(self, judge: LLMJudge | None = None) -> None:
        self._judge = judge or LLMJudge()

    async def _evaluate_sample(
        self,
        sample: EvalSample,
        dimensions: list[str],
        timeout_s: float,
    ) -> SampleResult:
        t0 = time.monotonic()
        try:
            judge_result = await asyncio.wait_for(
                self._judge.evaluate(
                    question=sample.question,
                    answer=sample.answer,
                    context=sample.context,
                    dimensions=dimensions,
                ),
                timeout=timeout_s,
            )
            return SampleResult(
                sample_id=sample.sample_id,
                judge_result=judge_result,
                duration_s=time.monotonic() - t0,
            )
        except TimeoutError:
            from .judge import JudgeResult

            return SampleResult(
                sample_id=sample.sample_id,
                judge_result=JudgeResult(
                    question=sample.question,
                    answer=sample.answer,
                    error="timeout",
                ),
                error="timeout",
                duration_s=time.monotonic() - t0,
            )
        except Exception as exc:
            logger.error(f"Sample {sample.sample_id} failed: {exc}")
            from .judge import JudgeResult

            return SampleResult(
                sample_id=sample.sample_id,
                judge_result=JudgeResult(
                    question=sample.question,
                    answer=sample.answer,
                    error=str(exc),
                ),
                error=str(exc),
                duration_s=time.monotonic() - t0,
            )

    async def run(self, config: EvalJobConfig) -> EvalJobResult:
        """Run a full evaluation job.

        Args:
            config: Job configuration including samples and dimensions.

        Returns:
            EvalJobResult with per-sample and aggregated scores.
        """
        started_at = time.time()
        logger.info(f"Starting eval job '{config.job_id}' ({len(config.samples)} samples)")

        sem = asyncio.Semaphore(config.max_concurrency)

        async def bounded(sample: EvalSample) -> SampleResult:
            async with sem:
                return await self._evaluate_sample(sample, config.dimensions, config.timeout_per_sample_s)

        sample_results: list[SampleResult] = await asyncio.gather(*[bounded(s) for s in config.samples])

        successful = [r for r in sample_results if r.error is None]
        failed_count = len(sample_results) - len(successful)

        # Compute averages per dimension
        def _avg(dim: str) -> float | None:
            vals = []
            for r in successful:
                s = getattr(r.judge_result, dim, None)
                if s is not None:
                    vals.append(s.score)
            return sum(vals) / len(vals) if vals else None

        avg_overall_vals = [r.judge_result.overall_score for r in successful if r.judge_result.overall_score is not None]

        # Build TraceMetrics for aggregation (latency only here)
        traces = [
            TraceMetrics(
                trace_id=r.sample_id,
                total_latency_s=r.duration_s,
                error_count=1 if r.error else 0,
            )
            for r in sample_results
        ]
        aggregated = aggregate_metrics(traces)

        completed_at = time.time()
        result = EvalJobResult(
            job_id=config.job_id,
            job_name=config.name,
            started_at=started_at,
            completed_at=completed_at,
            total_samples=len(config.samples),
            successful_samples=len(successful),
            failed_samples=failed_count,
            sample_results=sample_results,
            aggregated=aggregated,
            avg_relevance=_avg("relevance"),
            avg_groundedness=_avg("groundedness"),
            avg_coherence=_avg("coherence"),
            avg_overall=sum(avg_overall_vals) / len(avg_overall_vals) if avg_overall_vals else None,
        )

        avg_str = f"{result.avg_overall:.3f}" if result.avg_overall is not None else "n/a"
        logger.info(f"Eval job '{config.job_id}' complete: {len(successful)}/{len(sample_results)} OK, avg_overall={avg_str}")
        return result
