"""OctoAgent Evaluation System.

Provides LLM-as-Judge evaluation, trace metrics, batch evaluation runner,
and report generation. All modules are designed to work without external
dependencies beyond the standard library and the project's existing stack.
"""

from .judge import JudgeResult, JudgeScore, LLMJudge
from .metrics import AggregatedMetrics, TraceMetrics, aggregate_metrics
from .reporter import generate_json_report, generate_text_report
from .runner import EvalJobConfig, EvalJobResult, EvalSample, EvaluationRunner

__all__ = [
    "JudgeResult",
    "JudgeScore",
    "LLMJudge",
    "TraceMetrics",
    "AggregatedMetrics",
    "aggregate_metrics",
    "EvalSample",
    "EvalJobConfig",
    "EvalJobResult",
    "EvaluationRunner",
    "generate_json_report",
    "generate_text_report",
]
