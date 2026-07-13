"""System module status router.

GET /api/system/modules/status

Returns a JSON list of modules with status="ok"|"degraded"|"error" and an
``error_summary`` for fast UI rendering, plus an ``error_details`` payload that
the inspector tab can use as drill-down.

This endpoint is deliberately stateless and synchronous: each module probe must
return in <500ms or be skipped. New modules are appended to ``_PROBES``.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psutil
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])


def _thermal_sensors() -> list[dict[str, Any]]:
    sensors: list[dict[str, Any]] = []
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            value = float((zone / "temp").read_text().strip()) / 1000
            label = (zone / "type").read_text().strip()
        except (OSError, ValueError):
            continue
        if 0 < value < 150:
            sensors.append({"name": label, "temperature_c": round(value, 1)})
    return sensors


def _gpu_status() -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=False,
            encoding="utf-8",
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    name, utilization, used, total, temperature, power = [part.strip() for part in result.stdout.splitlines()[0].split(",")]

    def number(value: str) -> float:
        try:
            return float(value)
        except ValueError:
            return 0.0

    return {
        "name": name,
        "utilization_percent": number(utilization),
        "memory_used_mb": number(used),
        "memory_total_mb": number(total),
        "temperature_c": number(temperature),
        "power_w": number(power),
    }


def _service_status(name: str) -> dict[str, str]:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True,
            check=False,
            encoding="utf-8",
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"name": name, "status": "unknown"}
    return {"name": name, "status": result.stdout.strip() or "inactive"}


@router.get("/overview")
def system_overview() -> dict[str, Any]:
    """Small, read-only host overview for the workspace context panel."""
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    services = [_service_status(name) for name in ("octoagent-local.service", "clash-verge-service.service")]
    temperatures = _thermal_sensors()
    gpu = _gpu_status()
    overall = "ok" if all(item["status"] == "active" for item in services) else "degraded"
    return {
        "overall": overall,
        "generated_at": time.time(),
        "cpu": {"percent": psutil.cpu_percent(interval=0.1), "load": list(os.getloadavg())},
        "memory": {"percent": memory.percent, "used_bytes": memory.used, "total_bytes": memory.total},
        "disk": {"percent": disk.percent, "used_bytes": disk.used, "total_bytes": disk.total},
        "gpu": gpu,
        "temperatures": temperatures,
        "services": services,
        "network": {
            "proxy_configured": bool(os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")),
            "dns_over_tls": "+DNSOverTLS" in _command_output(["resolvectl", "status"]),
        },
    }


def _command_output(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, check=False, encoding="utf-8", timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout


def _probe(name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        out = fn() or {}
        status = out.pop("status", "ok")
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "module": name,
            "status": status,
            "elapsed_ms": elapsed,
            "details": out,
            "error_summary": out.get("error_summary"),
            "error_details": None,
        }
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "module": name,
            "status": "error",
            "elapsed_ms": elapsed,
            "details": None,
            "error_summary": f"{type(e).__name__}: {e}",
            "error_details": traceback.format_exc(),
        }


# ─── probes ────────────────────────────────────────────────────────────────────


def _probe_checkpointer() -> dict[str, Any]:
    from src.runtime.config.app_config import get_app_config

    cfg = get_app_config().checkpointer
    if cfg is None:
        return {"status": "ok", "type": "memory (default)"}
    info: dict[str, Any] = {"type": cfg.type}
    if cfg.type == "sqlite" and cfg.connection_string:
        p = Path(cfg.connection_string)
        info["path"] = str(p)
        info["exists"] = p.exists()
        info["size_bytes"] = p.stat().st_size if p.exists() else 0
    return info


def _probe_lessons_store() -> dict[str, Any]:
    from src.storage.self_evolution.lessons import LessonsStore

    store = LessonsStore.default()
    return {"status": "ok", "count": store.count(), "db": str(store.db_path)}


def _probe_openrouter_key() -> dict[str, Any]:
    k = os.getenv("OPENROUTER_API_KEY", "")
    if not k:
        return {"status": "error", "error_summary": "OPENROUTER_API_KEY not set"}
    if len(k) < 40:
        return {"status": "degraded", "error_summary": f"OPENROUTER_API_KEY length={len(k)} looks truncated"}
    return {"status": "ok", "key_len": len(k)}


def _probe_web_search_keys() -> dict[str, Any]:
    """Probe web search tooling.

    Primary path is now Tavily (Round F, 2026-05-14); DDG remains as a keyless
    fallback exposed as web_search_ddg / web_fetch_ddg.
    """
    out: dict[str, Any] = {}
    status = "ok"
    summary_parts: list[str] = []
    try:
        from src.community.tavily.tools import web_search_tool as _tavily  # noqa: F401

        out["tavily_loaded"] = True
    except Exception as e:
        out["tavily_loaded"] = False
        summary_parts.append(f"tavily import failed: {e.__class__.__name__}")
    try:
        from src.community.ddg.tools import web_search_tool as _ddg  # noqa: F401

        out["ddg_loaded"] = True
    except Exception as e:
        out["ddg_loaded"] = False
        summary_parts.append(f"ddg import failed: {e.__class__.__name__}")
    tav = os.getenv("TAVILY_API_KEY", "")
    out["tavily_key_present"] = bool(tav) and len(tav) >= 30 and not tav.startswith("your-")
    jin = os.getenv("JINA_API_KEY", "")
    out["jina_key_present"] = bool(jin) and len(jin) >= 30 and not jin.startswith("your-")
    out["http_proxy"] = bool(os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY"))
    out["primary"] = "tavily" if (out["tavily_loaded"] and out["tavily_key_present"]) else ("ddg" if out["ddg_loaded"] else "none")
    if out["primary"] == "none":
        status = "degraded"
        summary_parts.append("no working web_search provider")
    if summary_parts:
        out["error_summary"] = "; ".join(summary_parts)
    out["status"] = status
    return out


def _probe_self_evolution() -> dict[str, Any]:
    from src.storage.self_evolution import get_self_evolution_engine

    engine = get_self_evolution_engine()
    return {"status": "ok", "engine_loaded": engine is not None}


def _probe_workspace_db() -> dict[str, Any]:
    # Use absolute path relative to repo root (parents[5] from this file:
    # backend/src/gateway/routers/module_status.py -> repo root)
    repo_root = Path(__file__).resolve().parents[4]
    ws = repo_root / "workspace"
    if not ws.exists():
        return {"status": "degraded", "error_summary": f"workspace/ directory missing at {ws}"}
    return {
        "status": "ok",
        "path": str(ws),
        "lessons_db": (ws / "lessons.db").exists(),
        "checkpoints_db": (ws / "runtime" / "checkpoints.db").exists(),
    }


_PROBES: list[tuple[str, Callable[[], dict[str, Any]]]] = [
    ("checkpointer", _probe_checkpointer),
    ("lessons_store", _probe_lessons_store),
    ("openrouter_key", _probe_openrouter_key),
    ("web_search_keys", _probe_web_search_keys),
    ("self_evolution", _probe_self_evolution),
    ("workspace_db", _probe_workspace_db),
]


@router.get("/modules/status")
def modules_status() -> dict[str, Any]:
    """Quick startup-time module health probe.

    Each probe runs synchronously and is bounded by its own try/except so a
    failure in one module never breaks the response.
    """
    t0 = time.perf_counter()
    results = [_probe(name, fn) for name, fn in _PROBES]
    summary = {
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "degraded": sum(1 for r in results if r["status"] == "degraded"),
        "error": sum(1 for r in results if r["status"] == "error"),
    }
    overall = "ok"
    if summary["error"]:
        overall = "error"
    elif summary["degraded"]:
        overall = "degraded"
    return {
        "overall": overall,
        "summary": summary,
        "modules": results,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
