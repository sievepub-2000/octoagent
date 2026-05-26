"""Observation-only trust score ledger for skill invocations.

Design policy (from repo memory):
    自优化/自进化能力默认只能进入观测、建议、影子评估或灰度模式；
    未经验证不得直接改写生产默认策略。

This module therefore implements **only** the observation tier:

- ``record_invocation`` appends a JSON Lines entry to
  ``workspace/skill_evolution/trust_scores.jsonl`` describing one skill call.
- ``summarize_scores`` computes a rolling success-rate / latency / trust-score
  view over the ledger without ever mutating skill manifests.
- Guarded by ``SKILL_TRUST_OBSERVATION_ENABLED`` env var. Observation is on by
    default because it is append-only and does not change runtime policy; set the
    variable to ``0``/``false``/``off`` to disable it.

There is no promotion, demotion, or auto-swap logic here — that would require
explicit sign-off and belongs in a later graduation step.
"""

from __future__ import annotations

import json
import math
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.runtime.config.paths import Paths
from src.utils.datetime import utc_now_iso_z as _utc_now_iso

_LEDGER_LOCK = threading.Lock()
_ENV_FLAG = "SKILL_TRUST_OBSERVATION_ENABLED"
_DEFAULT_LEDGER_NAME = "trust_scores.jsonl"


def is_enabled() -> bool:
    return os.environ.get(_ENV_FLAG, "1").strip() not in {"", "0", "false", "False", "off", "no"}


def _resolve_ledger_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    override = os.environ.get("SKILL_TRUST_LEDGER_PATH")
    if override:
        return Path(override)
    return Paths().base_dir / "skill_evolution" / _DEFAULT_LEDGER_NAME




def record_invocation(
    skill_name: str,
    *,
    success: bool,
    latency_ms: float | None = None,
    extra: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> bool:
    """Append a trust-score observation. Returns True if written, False if disabled.

    Safe to call from hot paths: when disabled, returns immediately without
    touching disk. When enabled, appends a single JSON line under a lock so
    concurrent invocations do not interleave bytes.
    """

    if not is_enabled():
        return False
    if not skill_name:
        return False

    entry: dict[str, Any] = {
        "ts": _utc_now_iso(),
        "skill": str(skill_name),
        "success": bool(success),
    }
    if latency_ms is not None:
        try:
            entry["latency_ms"] = float(latency_ms)
        except (TypeError, ValueError):
            pass
    if extra:
        # Only accept primitives to keep the ledger line small and parseable.
        safe_extra: dict[str, Any] = {}
        for key, value in extra.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe_extra[str(key)] = value
        if safe_extra:
            entry["extra"] = safe_extra

    target = _resolve_ledger_path(ledger_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with _LEDGER_LOCK:
            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except OSError:
        # Best-effort observation; never raise into the caller's hot path.
        return False


def _wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    """95%% Wilson score lower bound. Conservative trust score for small N."""

    if total <= 0:
        return 0.0
    phat = successes / total
    denom = 1 + (z * z) / total
    centre = phat + (z * z) / (2 * total)
    margin = z * math.sqrt((phat * (1 - phat) + (z * z) / (4 * total)) / total)
    return max(0.0, (centre - margin) / denom)


def summarize_scores(
    ledger_path: Path | str | None = None,
    *,
    window: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Return per-skill aggregates: total, successes, success_rate, p95_latency_ms, trust_score.

    ``window`` optionally restricts to the last N observations (newest first).
    Returns an empty dict if the ledger does not exist.
    """

    path = _resolve_ledger_path(ledger_path)
    if not path.exists():
        return {}

    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if window is not None and window > 0:
        entries = entries[-window:]

    buckets: dict[str, dict[str, Any]] = {}
    for entry in entries:
        skill = str(entry.get("skill") or "")
        if not skill:
            continue
        bucket = buckets.setdefault(
            skill,
            {"total": 0, "successes": 0, "latencies": []},
        )
        bucket["total"] += 1
        if entry.get("success"):
            bucket["successes"] += 1
        latency = entry.get("latency_ms")
        if isinstance(latency, (int, float)):
            bucket["latencies"].append(float(latency))

    out: dict[str, dict[str, Any]] = {}
    for skill, bucket in buckets.items():
        total = bucket["total"]
        successes = bucket["successes"]
        latencies = sorted(bucket["latencies"])
        p95 = latencies[int(0.95 * (len(latencies) - 1))] if latencies else None
        out[skill] = {
            "total": total,
            "successes": successes,
            "success_rate": (successes / total) if total else 0.0,
            "p95_latency_ms": p95,
            "trust_score": _wilson_lower_bound(successes, total),
        }
    return out


__all__ = ["is_enabled", "record_invocation", "summarize_scores"]
