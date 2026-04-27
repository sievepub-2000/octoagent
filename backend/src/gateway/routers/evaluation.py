"""Evaluation REST API router for OctoAgent.

Provides endpoints to manage and run LLM-as-Judge evaluation jobs.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.evaluation import (
    EvalJobConfig,
    EvalSample,
    EvaluationRunner,
    LLMJudge,
    generate_json_report,
)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


# ──────────────────────────── Request / Response models ─────────────────────


class SampleRequest(BaseModel):
    sample_id: str = Field(default="", description="Unique identifier; auto-generated if empty")
    question: str
    answer: str
    context: str = ""
    ground_truth: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunJobRequest(BaseModel):
    job_id: str = Field(default="", description="Unique job ID; auto-generated if empty")
    name: str = Field(default="adhoc", description="Human-readable job name")
    samples: list[SampleRequest]
    dimensions: list[str] = Field(
        default=["relevance", "groundedness", "coherence"],
        description="Which judge dimensions to evaluate",
    )
    max_concurrency: int = Field(default=3, ge=1, le=20)
    timeout_per_sample_s: float = Field(default=30.0, ge=0.5, le=300.0)


class JobSummaryResponse(BaseModel):
    job_id: str
    job_name: str
    total_samples: int
    successful_samples: int
    failed_samples: int
    duration_s: float
    avg_relevance: float | None
    avg_groundedness: float | None
    avg_coherence: float | None
    avg_overall: float | None


# ──────────────────────────── Endpoints ──────────────────────────────────────


@router.post("/jobs/run", response_model=dict[str, Any], summary="Run a new evaluation job")
async def run_evaluation_job(request: RunJobRequest) -> dict[str, Any]:
    """Run an evaluation job over a list of (question, answer) samples.

    Each sample is scored on the requested judge dimensions.
    Returns the full job result including per-sample scores.
    """
    samples = []
    for i, s in enumerate(request.samples):
        sid = s.sample_id or f"sample-{i:04d}"
        samples.append(
            EvalSample(
                sample_id=sid,
                question=s.question,
                answer=s.answer,
                context=s.context,
                ground_truth=s.ground_truth,
                metadata=s.metadata,
            )
        )

    if not samples:
        raise HTTPException(status_code=422, detail="At least one sample is required")

    valid_dims = {"relevance", "groundedness", "coherence"}
    bad_dims = set(request.dimensions) - valid_dims
    if bad_dims:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown dimensions: {sorted(bad_dims)}. Valid: {sorted(valid_dims)}",
        )

    job_id = request.job_id or f"job-{int(time.time())}"
    config = EvalJobConfig(
        job_id=job_id,
        name=request.name,
        samples=samples,
        dimensions=request.dimensions,
        max_concurrency=request.max_concurrency,
        timeout_per_sample_s=request.timeout_per_sample_s,
    )

    runner = EvaluationRunner(judge=LLMJudge(llm_callable=None))
    result = await runner.run(config)
    return generate_json_report(result)


@router.post("/jobs/run/summary", response_model=JobSummaryResponse, summary="Run a job, return summary only")
async def run_evaluation_job_summary(request: RunJobRequest) -> JobSummaryResponse:
    """Run an evaluation job and return only the summary (no per-sample details)."""
    samples = [
        EvalSample(
            sample_id=s.sample_id or f"sample-{i:04d}",
            question=s.question,
            answer=s.answer,
            context=s.context,
        )
        for i, s in enumerate(request.samples)
    ]

    if not samples:
        raise HTTPException(status_code=422, detail="At least one sample is required")

    job_id = request.job_id or f"job-{int(time.time())}"
    config = EvalJobConfig(
        job_id=job_id,
        name=request.name,
        samples=samples,
        dimensions=request.dimensions,
        max_concurrency=request.max_concurrency,
        timeout_per_sample_s=request.timeout_per_sample_s,
    )

    runner = EvaluationRunner(judge=LLMJudge(llm_callable=None))
    result = await runner.run(config)

    return JobSummaryResponse(
        job_id=result.job_id,
        job_name=result.job_name,
        total_samples=result.total_samples,
        successful_samples=result.successful_samples,
        failed_samples=result.failed_samples,
        duration_s=result.completed_at - result.started_at,
        avg_relevance=result.avg_relevance,
        avg_groundedness=result.avg_groundedness,
        avg_coherence=result.avg_coherence,
        avg_overall=result.avg_overall,
    )


@router.post("/score", response_model=dict[str, Any], summary="Score a single response")
async def score_single(
    question: str,
    answer: str,
    context: str = "",
    dimensions: str = "relevance,groundedness,coherence",
) -> dict[str, Any]:
    """Score a single (question, answer) pair with LLM-as-Judge."""
    dims = [d.strip() for d in dimensions.split(",") if d.strip()]
    valid = {"relevance", "groundedness", "coherence"}
    bad = set(dims) - valid
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown dimensions: {sorted(bad)}")

    judge = LLMJudge(llm_callable=None)
    result = await judge.evaluate(question=question, answer=answer, context=context, dimensions=dims)
    return result.to_dict()


@router.get("/health", response_model=dict[str, str], summary="Evaluation service health check")
async def eval_health() -> dict[str, str]:
    """Return health status of the evaluation service."""
    return {"status": "ok", "service": "evaluation"}
