"""Memory monitor for tracking and optimizing system memory usage.

Monitors memory usage trends and triggers recycling when thresholds are exceeded.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MemorySnapshot:
    """Snapshot of current memory usage."""

    timestamp: float
    total_memory_mb: float
    used_memory_mb: float
    free_memory_mb: float
    percent_used: float
    cache_mb: float
    swap_total_mb: float
    swap_used_mb: float


class MemoryMonitor:
    """Monitors system memory usage and triggers recycling when needed."""

    def __init__(
        self,
        high_threshold_percent: float = 80.0,
        critical_threshold_percent: float = 90.0,
        check_interval_seconds: float = 60.0,
    ) -> None:
        self._high_threshold = high_threshold_percent
        self._critical_threshold = critical_threshold_percent
        self._check_interval = check_interval_seconds
        self._last_check_time = 0.0
        self._snapshots: list[MemorySnapshot] = []
        self._max_snapshots = 1000
        self._recycling_triggered = 0
        self._stats: dict[str, Any] = {
            "total_checks": 0,
            "high_threshold_hits": 0,
            "critical_threshold_hits": 0,
            "last_check_at": None,
            "last_status": "unknown",
        }

    def get_snapshot(self) -> MemorySnapshot:
        """Get current memory usage snapshot."""
        try:
            # Get system memory info from /proc/meminfo
            total_mb = 0
            free_mb = 0
            cache_mb = 0
            swap_total_mb = 0
            swap_used_mb = 0

            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total_mb = int(line.split()[1]) / 1024
                    elif line.startswith("MemFree:"):
                        free_mb = int(line.split()[1]) / 1024
                    elif line.startswith("Buffers:"):
                        cache_mb += int(line.split()[1]) / 1024
                    elif line.startswith("Cached:"):
                        cache_mb += int(line.split()[1]) / 1024
                    elif line.startswith("SwapTotal:"):
                        swap_total_mb = int(line.split()[1]) / 1024
                    elif line.startswith("SwapFree:"):
                        swap_used_mb = (int(line.split()[1]) / 1024) - swap_total_mb

            used_mb = total_mb - free_mb - cache_mb
            percent_used = (used_mb / total_mb * 100) if total_mb > 0 else 0

            snapshot = MemorySnapshot(
                timestamp=time.time(),
                total_memory_mb=total_mb,
                used_memory_mb=used_mb,
                free_memory_mb=free_mb,
                percent_used=percent_used,
                cache_mb=cache_mb,
                swap_total_mb=swap_total_mb,
                swap_used_mb=swap_used_mb,
            )

            self._snapshots.append(snapshot)
            if len(self._snapshots) > self._max_snapshots:
                self._snapshots = self._snapshots[-self._max_snapshots :]

            return snapshot

        except Exception as exc:
            logger.error("Failed to get memory snapshot: %s", exc)
            return MemorySnapshot(
                timestamp=time.time(),
                total_memory_mb=0,
                used_memory_mb=0,
                free_memory_mb=0,
                percent_used=0,
                cache_mb=0,
                swap_total_mb=0,
                swap_used_mb=0,
            )

    def check_and_trigger_recycle(self, recycle_func: callable) -> dict[str, Any]:
        """Check memory usage and trigger recycling if thresholds are exceeded.

        Args:
            recycle_func: Function to call for recycling.

        Returns:
            Dictionary with recycling results.
        """
        self._stats["total_checks"] += 1
        self._last_check_time = time.time()

        snapshot = self.get_snapshot()

        status = "normal"
        if snapshot.percent_used >= self._critical_threshold:
            status = "critical"
            self._stats["critical_threshold_hits"] += 1
        elif snapshot.percent_used >= self._high_threshold:
            status = "high"
            self._stats["high_threshold_hits"] += 1

        self._stats["last_status"] = status
        self._stats["last_check_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        result = {"snapshot": snapshot, "status": status, "recycled": False}

        if status in ("high", "critical"):
            logger.warning(
                "Memory usage %.2f%% exceeds threshold (%s), triggering recycling",
                snapshot.percent_used,
                status,
            )
            recycle_result = recycle_func()
            result["recycled"] = True
            result["recycle_result"] = recycle_result
            self._recycling_triggered += 1

        return result

    def get_trend(self) -> dict[str, Any]:
        """Get memory usage trend analysis."""
        if len(self._snapshots) < 2:
            return {"trend": "insufficient_data", "snapshots_count": len(self._snapshots)}

        # Calculate trend from recent snapshots
        recent = self._snapshots[-10:]  # Last 10 snapshots
        timestamps = [s.timestamp for s in recent]
        percentages = [s.percent_used for s in recent]

        if len(timestamps) < 2:
            return {"trend": "insufficient_data", "snapshots_count": len(recent)}

        # Simple linear regression
        n = len(timestamps)
        sum_x = sum(timestamps)
        sum_y = sum(percentages)
        sum_xy = sum(x * y for x, y in zip(timestamps, percentages))
        sum_x2 = sum(x * x for x in timestamps)

        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return {"trend": "stable", "slope": 0.0, "snapshots_count": n}

        slope = (n * sum_xy - sum_x * sum_y) / denominator

        if slope > 0.1:
            trend = "increasing"
        elif slope < -0.1:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "slope": slope,
            "current_percent": percentages[-1],
            "snapshots_count": n,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get memory monitor statistics."""
        return {
            **self._stats,
            "high_threshold_percent": self._high_threshold,
            "critical_threshold_percent": self._critical_threshold,
            "snapshot_count": len(self._snapshots),
            "recycling_triggered": self._recycling_triggered,
        }


# Singleton instance
_monitor: MemoryMonitor | None = None


def get_memory_monitor(
    high_threshold_percent: float = 80.0,
    critical_threshold_percent: float = 90.0,
) -> MemoryMonitor:
    """Get or create the singleton MemoryMonitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = MemoryMonitor(
            high_threshold_percent=high_threshold_percent,
            critical_threshold_percent=critical_threshold_percent,
        )
    return _monitor
