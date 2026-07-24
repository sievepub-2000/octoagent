"""Lightweight Prometheus-compatible metrics for OctoAgent.

Exposes /metrics in text/plain exposition format (no external dependency).
"""

from __future__ import annotations

import logging
from threading import Lock

logger = logging.getLogger(__name__)


class _Counter:
    __slots__ = ("_value", "_lock")

    def __init__(self) -> None:
        self._value = 0.0
        self._lock = Lock()

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        return self._value


class _Gauge:
    __slots__ = ("_value", "_lock")

    def __init__(self) -> None:
        self._value = 0.0
        self._lock = Lock()

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value -= amount

    @property
    def value(self) -> float:
        return self._value


class _Histogram:
    """Fixed-bucket histogram for latency tracking."""

    __slots__ = ("_buckets", "_sum", "_count", "_lock")

    BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)

    def __init__(self) -> None:
        self._buckets: dict[float, int] = {b: 0 for b in self.BUCKETS}
        self._sum = 0.0
        self._count = 0
        self._lock = Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._sum += value
            self._count += 1
            for b in self.BUCKETS:
                if value <= b:
                    self._buckets[b] += 1


class MetricsRegistry:
    """Central metrics registry."""

    def __init__(self) -> None:
        self._counters: dict[str, _Counter] = {}
        self._gauges: dict[str, _Gauge] = {}
        self._histograms: dict[str, _Histogram] = {}
        self._help: dict[str, str] = {}
        self._lock = Lock()

    def counter(self, name: str, help_text: str = "") -> _Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = _Counter()
                self._help[name] = help_text
            return self._counters[name]

    def gauge(self, name: str, help_text: str = "") -> _Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = _Gauge()
                self._help[name] = help_text
            return self._gauges[name]

    def histogram(self, name: str, help_text: str = "") -> _Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = _Histogram()
                self._help[name] = help_text
            return self._histograms[name]

    def increment(self, name: str, *, amount: float = 1.0, labels: dict | None = None) -> float:
        """Increment (or create) a counter by *amount*. Returns the new value."""
        c = self.counter(name)
        c.inc(amount)
        return c.value

    def reset(self, name: str) -> None:
        """Reset a counter to 0. Raises KeyError if not found."""
        with self._lock:
            if name not in self._counters:
                raise KeyError(name)
            self._counters[name]._value = 0.0

    def snapshot(self) -> list[dict]:
        """Return all counter values as a list of dicts for JSON serialisation."""
        results: list[dict] = []
        with self._lock:
            for name, c in self._counters.items():
                results.append({"name": name, "value": c.value, "kind": "counter", "labels": {}})
            for name, g in self._gauges.items():
                results.append({"name": name, "value": g.value, "kind": "gauge", "labels": {}})
        return results

    def render(self) -> str:
        """Render all metrics in Prometheus text exposition format."""
        lines: list[str] = []

        for name, c in sorted(self._counters.items()):
            if self._help.get(name):
                lines.append(f"# HELP {name} {self._help[name]}")
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {c.value}")

        for name, g in sorted(self._gauges.items()):
            if self._help.get(name):
                lines.append(f"# HELP {name} {self._help[name]}")
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {g.value}")

        for name, h in sorted(self._histograms.items()):
            if self._help.get(name):
                lines.append(f"# HELP {name} {self._help[name]}")
            lines.append(f"# TYPE {name} histogram")
            cumulative = 0
            for b in _Histogram.BUCKETS:
                cumulative += h._buckets.get(b, 0)
                lines.append(f'{name}_bucket{{le="{b}"}} {cumulative}')
            lines.append(f'{name}_bucket{{le="+Inf"}} {h._count}')
            lines.append(f"{name}_sum {h._sum}")
            lines.append(f"{name}_count {h._count}")

        return "\n".join(lines) + "\n"


# ---------- Global singleton ----------

_registry: MetricsRegistry | None = None


def get_metrics_registry() -> MetricsRegistry:
    global _registry
    if _registry is None:
        _registry = MetricsRegistry()
        _setup_default_metrics(_registry)
    return _registry


def _setup_default_metrics(reg: MetricsRegistry) -> None:
    """Pre-register common OctoAgent metrics."""
    reg.counter("octoagent_requests_total", "Total HTTP requests processed")
    reg.counter("octoagent_task_completed_total", "Total tasks completed")
    reg.counter("octoagent_task_failed_total", "Total tasks failed")
    reg.histogram("octoagent_request_duration_seconds", "HTTP request duration in seconds")
