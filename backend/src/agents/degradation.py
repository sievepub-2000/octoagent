"""Auto-degradation controller — throttles agent capabilities under resource pressure.

Reads CPU + memory utilization via psutil and exposes a simple degradation
level that middlewares can query to adjust concurrency, LLM calls, and
streaming behaviour at runtime without a restart.

Levels:
  normal  — everything at full capacity
  mild    — soft limits (reduced concurrency, longer debounce)
  heavy   — aggressive limits (streaming off, skip non-essential LLM calls)
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# Thresholds (percentage)
_CPU_MILD = 70.0
_CPU_HEAVY = 88.0
_MEM_MILD = 75.0
_MEM_HEAVY = 90.0

# How long to cache the reading before probing again (seconds)
_CACHE_TTL = 5.0

DegradationLevel = str  # "normal" | "mild" | "heavy"


class DegradationController:
    """Lightweight background sampler of CPU / memory pressure."""

    def __init__(self) -> None:
        self._level: DegradationLevel = "normal"
        self._lock = threading.Lock()
        self._last_check: float = 0.0
        self._psutil_available = self._check_psutil()

    def _check_psutil(self) -> bool:
        try:
            import psutil  # noqa: F401

            return True
        except ImportError:
            logger.warning("psutil not installed — DegradationController will always report 'normal'")
            return False

    def get_level(self) -> DegradationLevel:
        """Return current degradation level (cached for 5s)."""
        now = time.monotonic()
        with self._lock:
            if now - self._last_check < _CACHE_TTL:
                return self._level
        level = self._probe()
        with self._lock:
            self._level = level
            self._last_check = now
        return level

    def _probe(self) -> DegradationLevel:
        if not self._psutil_available:
            return "normal"
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=0.2)
            mem = psutil.virtual_memory().percent
        except Exception:
            return "normal"

        if cpu >= _CPU_HEAVY or mem >= _MEM_HEAVY:
            level: DegradationLevel = "heavy"
        elif cpu >= _CPU_MILD or mem >= _MEM_MILD:
            level = "mild"
        else:
            level = "normal"

        if level != "normal":
            logger.debug("DegradationController: level=%s cpu=%.1f%% mem=%.1f%%", level, cpu, mem)
        return level

    @property
    def is_degraded(self) -> bool:
        return self.get_level() != "normal"

    @property
    def is_heavy(self) -> bool:
        return self.get_level() == "heavy"


_controller: DegradationController | None = None
_controller_lock = threading.Lock()


def get_degradation_controller() -> DegradationController:
    """Return the global singleton DegradationController."""
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:
                _controller = DegradationController()
    return _controller


def get_degradation_level() -> DegradationLevel:
    """Convenience wrapper — returns 'normal', 'mild', or 'heavy'."""
    return get_degradation_controller().get_level()


# ---- Critical-pressure abort guard ------------------------------------------
# The only hard abort is host memory pressure. CPU pressure remains a soft
# degradation signal; task execution is stopped by runtime_oom_guard at 90% RAM.
_ABORT_MEM = float(os.environ.get("OCTO_OOM_STOP_MEM_PERCENT", os.environ.get("OCTO_RESOURCE_ABORT_MEM", "90")))


def _probe_raw() -> tuple[float, float]:
    try:
        import psutil

        return psutil.cpu_percent(interval=0.0), psutil.virtual_memory().percent
    except Exception:
        return 0.0, 0.0


def should_abort() -> bool:
    """True only when memory usage reaches the hard OOM stop threshold."""
    cpu, mem = _probe_raw()
    crit = mem >= _ABORT_MEM
    if crit:
        logger.warning(
            "Memory pressure abort: cpu=%.1f%% mem=%.1f%% (limit mem>=%.0f%%)",
            cpu,
            mem,
            _ABORT_MEM,
        )
    return crit


def resource_snapshot() -> dict:
    cpu, mem = _probe_raw()
    return {
        "cpu_percent": cpu,
        "mem_percent": mem,
        "abort_cpu_threshold": None,
        "abort_mem_threshold": _ABORT_MEM,
        "level": get_degradation_level(),
    }
