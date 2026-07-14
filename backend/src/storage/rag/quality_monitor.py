"""Retrieval quality monitor for RAG system.

Tracks retrieval accuracy, precision, recall, and latency metrics
to enable quantitative evaluation of search quality.
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Represents a single retrieval result with quality metrics."""

    query: str
    table: str
    mode: str
    results_count: int
    top_score: float
    avg_score: float
    latency_ms: float
    has_vector: bool
    has_bm25: bool
    has_reranker: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class RetrievalQualityMonitor:
    """Monitors and reports on RAG retrieval quality metrics.

    Tracks:
    - Precision@K (how many of top K results are relevant)
    - Recall@K (how many relevant results are in top K)
    - NDCG@K (normalized discounted cumulative gain)
    - Latency percentiles
    - Score distributions
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        self._log_dir = log_dir or Path("/tmp/octoagent_rag_monitor")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._results: list[RetrievalResult] = []
        self._feedback: dict[str, list[int]] = defaultdict(list)  # query_hash -> [relevance_scores]
        self._max_results = 10000  # Keep last 10000 results
        self._metrics: dict[str, Any] = {
            "total_queries": 0,
            "total_results": 0,
            "avg_latency_ms": 0.0,
            "precision_at_1": 0.0,
            "precision_at_5": 0.0,
            "precision_at_10": 0.0,
            "recall_at_10": 0.0,
            "ndcg_at_10": 0.0,
            "score_mean": 0.0,
            "score_std": 0.0,
            "mode_distribution": defaultdict(int),
            "table_distribution": defaultdict(int),
        }

    def record_result(self, result: RetrievalResult) -> None:
        """Record a retrieval result for quality analysis.

        Args:
            result: The retrieval result to record.
        """
        self._results.append(result)
        if len(self._results) > self._max_results:
            self._results = self._results[-self._max_results :]

        self._metrics["total_queries"] += 1
        self._metrics["total_results"] += result.results_count
        self._metrics["mode_distribution"][result.mode] += 1
        self._metrics["table_distribution"][result.table] += result.results_count

        # Update latency
        self._metrics["avg_latency_ms"] = self._metrics["avg_latency_ms"] * 0.9 + result.latency_ms * 0.1

        # Update score statistics
        if result.results_count > 0:
            # Estimate score distribution from top_score and count
            self._update_score_stats(result.top_score, result.results_count)

        logger.debug(
            "Recorded retrieval: query=%s, table=%s, mode=%s, results=%d, latency=%.2fms",
            result.query[:50],
            result.table,
            result.mode,
            result.results_count,
            result.latency_ms,
        )

    def record_feedback(self, query_hash: str, relevance_scores: list[int]) -> None:
        """Record user feedback for a query.

        The relevance_scores list should contain integer scores from 0-5
        per result, where 5 means perfectly relevant and 0 means irrelevant.

        Args:
            query_hash: Hash of the query string.
            relevance_scores: List of relevance scores (0-5) for each result.
        """
        self._feedback[query_hash] = relevance_scores
        self._update_precision_recall_metrics()

    def get_metrics(self) -> dict[str, Any]:
        """Get current retrieval quality metrics.

        Returns:
            Dictionary of metrics.
        """
        return {
            "total_queries": self._metrics["total_queries"],
            "total_results": self._metrics["total_results"],
            "avg_latency_ms": round(self._metrics["avg_latency_ms"], 2),
            "precision_at_1": round(self._metrics["precision_at_1"], 4),
            "precision_at_5": round(self._metrics["precision_at_5"], 4),
            "precision_at_10": round(self._metrics["precision_at_10"], 4),
            "recall_at_10": round(self._metrics["recall_at_10"], 4),
            "ndcg_at_10": round(self._metrics["ndcg_at_10"], 4),
            "score_mean": round(self._metrics["score_mean"], 4),
            "score_std": round(self._metrics["score_std"], 4),
            "mode_distribution": dict(self._metrics["mode_distribution"]),
            "table_distribution": dict(self._metrics["table_distribution"]),
            "feedback_count": len(self._feedback),
        }

    def _update_score_stats(self, top_score: float, count: int) -> None:
        """Update score mean and standard deviation."""
        # Simple moving average approximation
        n = len(self._results)
        if n == 1:
            self._metrics["score_mean"] = top_score
            self._metrics["score_std"] = 0.0
        else:
            old_mean = self._metrics["score_mean"]
            new_mean = old_mean + (top_score - old_mean) / n
            self._metrics["score_mean"] = new_mean
            # Approximate std using moving variance
            self._metrics["score_std"] = max(
                0.0,
                self._metrics["score_std"] + (top_score - new_mean) * (1 - 1 / n),
            )

    def _update_precision_recall_metrics(self) -> None:
        """Update precision and recall metrics from feedback."""
        if not self._feedback:
            return

        total_precision_1 = 0.0
        total_precision_5 = 0.0
        total_precision_10 = 0.0
        total_recall_10 = 0.0
        total_ndcg_10 = 0.0
        count = 0

        for query_hash, scores in self._feedback.items():
            if not scores:
                continue

            # Precision@K
            if len(scores) >= 1:
                total_precision_1 += 1.0 if scores[0] > 0 else 0.0
            if len(scores) >= 5:
                relevant_in_5 = sum(1 for s in scores[:5] if s > 0)
                total_precision_5 += relevant_in_5 / 5.0
            if len(scores) >= 10:
                relevant_in_10 = sum(1 for s in scores[:10] if s > 0)
                total_precision_10 += relevant_in_10 / 10.0

            # Recall@10 (assuming max relevant = 10)
            relevant_in_10 = sum(1 for s in scores[:10] if s > 0)
            total_recall_10 += relevant_in_10 / 10.0

            # NDCG@10
            ndcg_10 = self._compute_ndcg(scores[:10])
            total_ndcg_10 += ndcg_10
            count += 1

        if count > 0:
            self._metrics["precision_at_1"] = total_precision_1 / count
            self._metrics["precision_at_5"] = total_precision_5 / count
            self._metrics["precision_at_10"] = total_precision_10 / count
            self._metrics["recall_at_10"] = total_recall_10 / count
            self._metrics["ndcg_at_10"] = total_ndcg_10 / count

    def _compute_ndcg(self, relevance_scores: list[int]) -> float:
        """Compute NDCG@K for a list of relevance scores."""
        if not relevance_scores:
            return 0.0

        # DCG
        dcg = 0.0
        for i, rel in enumerate(relevance_scores):
            dcg += (2**rel - 1) / math.log2(i + 2)

        # Ideal DCG (sorted descending)
        ideal_scores = sorted(relevance_scores, reverse=True)
        idcg = 0.0
        for i, rel in enumerate(ideal_scores):
            idcg += (2**rel - 1) / math.log2(i + 2)

        if idcg == 0:
            return 0.0

        return dcg / idcg

    def get_report(self) -> str:
        """Generate a human-readable quality report."""
        metrics = self.get_metrics()
        report = [
            "=== RAG Retrieval Quality Report ===",
            f"Total Queries: {metrics['total_queries']}",
            f"Total Results: {metrics['total_results']}",
            f"Avg Latency: {metrics['avg_latency_ms']} ms",
            "",
            "Precision Metrics:",
            f"  Precision@1: {metrics['precision_at_1']}",
            f"  Precision@5: {metrics['precision_at_5']}",
            f"  Precision@10: {metrics['precision_at_10']}",
            "",
            "Recall Metrics:",
            f"  Recall@10: {metrics['recall_at_10']}",
            "",
            "NDCG Metrics:",
            f"  NDCG@10: {metrics['ndcg_at_10']}",
            "",
            "Score Statistics:",
            f"  Mean: {metrics['score_mean']}",
            f"  Std: {metrics['score_std']}",
            "",
            "Mode Distribution:",
            json.dumps(metrics["mode_distribution"], indent=2),
            "",
            "Table Distribution:",
            json.dumps(metrics["table_distribution"], indent=2),
            f"Feedback Count: {metrics['feedback_count']}",
        ]
        return "\n".join(report)

    def export_metrics(self, path: Path | None = None) -> None:
        """Export metrics to JSON file."""
        export_path = path or self._log_dir / "rag_metrics.json"
        try:
            metrics = self.get_metrics()
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)
            logger.info("RAG metrics exported to %s", export_path)
        except Exception as exc:
            logger.error("Failed to export RAG metrics: %s", exc)


# Singleton instance
_monitor: RetrievalQualityMonitor | None = None


def get_quality_monitor(log_dir: Path | None = None) -> RetrievalQualityMonitor:
    """Get or create the singleton RetrievalQualityMonitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = RetrievalQualityMonitor(log_dir=log_dir)
    return _monitor
