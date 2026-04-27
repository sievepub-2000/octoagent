from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.optimization_program import (
    AuditDimension,
    AuditScorecard,
    BenchmarkMetric,
    ModuleWorkstream,
    OptimizationProgram,
    get_optimization_program,
)

router = APIRouter(prefix="/api/optimization", tags=["optimization"])


class OptimizationRoadmapResponse(BaseModel):
    workstreams: list[ModuleWorkstream] = Field(default_factory=list)


class OptimizationMetricsResponse(BaseModel):
    metrics: list[BenchmarkMetric] = Field(default_factory=list)


class OptimizationScorecardResponse(BaseModel):
    total_score: int
    release_gate: str
    dimensions: list[AuditDimension] = Field(default_factory=list)


@router.get("/program", response_model=OptimizationProgram)
async def get_program() -> OptimizationProgram:
    return get_optimization_program()


@router.get("/roadmap", response_model=OptimizationRoadmapResponse)
async def get_roadmap() -> OptimizationRoadmapResponse:
    program = get_optimization_program()
    return OptimizationRoadmapResponse(workstreams=program.roadmap)


@router.get("/scorecard", response_model=OptimizationScorecardResponse)
async def get_scorecard() -> OptimizationScorecardResponse:
    program = get_optimization_program()
    scorecard: AuditScorecard = program.scorecard
    return OptimizationScorecardResponse(
        total_score=scorecard.total_score,
        release_gate=scorecard.release_gate,
        dimensions=scorecard.dimensions,
    )


@router.get("/metrics", response_model=OptimizationMetricsResponse)
async def get_metrics() -> OptimizationMetricsResponse:
    program = get_optimization_program()
    return OptimizationMetricsResponse(metrics=program.metrics)