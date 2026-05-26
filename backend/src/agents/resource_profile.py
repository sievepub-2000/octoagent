"""Hardware-aware resource profile.

Computes sensible defaults for recursion limits, timeouts and concurrency at
process startup based on the actual hardware of the host the service runs on,
so the same code works on a 4 GB VM and a 128 GB workstation without manual
tuning.

The values are *recommended defaults*, not stop conditions. LangGraph itself
requires ``recursion_limit >= 1``; OctoAgent keeps the runtime limit at the
largest JSON-safe value and lets the OOM guard be the only hard safety stop.

Override via env (useful for tests / containers with cgroup limits the host
psutil reading does not see):

* ``OCTO_TIER``                  — force tier: tiny|small|medium|large
* ``OCTO_RECURSION_DEFAULT``     — recommended recursion_limit
* ``OCTO_TIMEOUT_DEFAULT_S``     — default per-step timeout
* ``OCTO_WORKSPACE_TIMEOUT_S``   — single-task workspace timeout
* ``OCTO_WORKSPACE_BRANCH_TIMEOUT_S`` — branch/group workspace timeout
* ``OCTO_WORKSPACE_RECURSION``   — workspace recursion default
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from typing import Literal

logger = logging.getLogger(__name__)

Tier = Literal["tiny", "small", "medium", "large"]

# LangGraph hard validation: recursion_limit must be >= 1.
# Any number passed must be a positive int. We never go above this absolute
# ceiling because there is no realistic agent run that would benefit, and it
# keeps the value JSON-safe.
ABSOLUTE_RECURSION_CEILING = 1_000_000_000


@dataclass(frozen=True)
class ResourceProfile:
    total_mem_gb: float
    cpu_cores: int
    tier: Tier
    # Recommended defaults — all callers should read from here instead of
    # baking in magic numbers.
    recursion_default: int
    timeout_default_s: int
    workspace_timeout_s: int
    workspace_branch_timeout_s: int
    workspace_recursion_default: int
    # Absolute safety ceiling enforced by LangGraph (>=1).
    recursion_ceiling: int = ABSOLUTE_RECURSION_CEILING

    def to_dict(self) -> dict:
        return asdict(self)


def _detect_hardware() -> tuple[float, int]:
    """Return (total_mem_gb, cpu_cores). Falls back if psutil unavailable."""
    try:
        import psutil  # type: ignore

        mem_gb = psutil.virtual_memory().total / (1024**3)
        cores = psutil.cpu_count(logical=True) or os.cpu_count() or 1
        return mem_gb, cores
    except Exception:
        # Conservative fallback — assume small host
        return 2.0, os.cpu_count() or 1


def _classify(mem_gb: float, cores: int) -> Tier:
    if mem_gb < 4 or cores < 2:
        return "tiny"
    if mem_gb < 16:
        return "small"
    if mem_gb < 64:
        return "medium"
    return "large"


# Tier defaults are advisory. Recursion defaults deliberately use the absolute
# ceiling so LangGraph does not stop long jobs solely because a step counter was
# reached; memory pressure is handled by runtime_oom_guard instead.
_TIER_DEFAULTS: dict[Tier, dict[str, int]] = {
    # tiny: <4GB RAM or <2 cores — Raspberry-Pi-class, single-tenant only
    "tiny": {
        "recursion_default": 2_000,
        "timeout_default_s": 60,
        "workspace_timeout_s": 120,
        "workspace_branch_timeout_s": 600,
        "workspace_recursion_default": 5_000,
    },
    # small: 4-16GB — modest laptop / small VM
    "small": {
        "recursion_default": 5_000,
        "timeout_default_s": 300,
        "workspace_timeout_s": 600,
        "workspace_branch_timeout_s": 1800,
        "workspace_recursion_default": 10_000,
    },
    # medium: 16-64GB — workstation / mid server
    "medium": {
        "recursion_default": 10_000,
        "timeout_default_s": 900,
        "workspace_timeout_s": 1800,
        "workspace_branch_timeout_s": 7200,
        "workspace_recursion_default": 20_000,
    },
    # large: >=64GB — dedicated server
    "large": {
        "recursion_default": 20_000,
        "timeout_default_s": 1800,
        "workspace_timeout_s": 3600,
        "workspace_branch_timeout_s": 14_400,
        "workspace_recursion_default": 50_000,
    },
}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v >= 1 else default
    except ValueError:
        return default


def _compute_profile() -> ResourceProfile:
    mem_gb, cores = _detect_hardware()
    tier = os.environ.get("OCTO_TIER") or _classify(mem_gb, cores)  # type: ignore[assignment]
    if tier not in _TIER_DEFAULTS:
        tier = _classify(mem_gb, cores)
    defaults = _TIER_DEFAULTS[tier]  # type: ignore[index]

    profile = ResourceProfile(
        total_mem_gb=round(mem_gb, 2),
        cpu_cores=cores,
        tier=tier,  # type: ignore[arg-type]
        recursion_default=min(
            _env_int("OCTO_RECURSION_DEFAULT", defaults["recursion_default"]),
            ABSOLUTE_RECURSION_CEILING,
        ),
        timeout_default_s=_env_int("OCTO_TIMEOUT_DEFAULT_S", defaults["timeout_default_s"]),
        workspace_timeout_s=_env_int("OCTO_WORKSPACE_TIMEOUT_S", defaults["workspace_timeout_s"]),
        workspace_branch_timeout_s=_env_int("OCTO_WORKSPACE_BRANCH_TIMEOUT_S", defaults["workspace_branch_timeout_s"]),
        workspace_recursion_default=min(
            _env_int("OCTO_WORKSPACE_RECURSION", defaults["workspace_recursion_default"]),
            ABSOLUTE_RECURSION_CEILING,
        ),
    )
    logger.info(
        "ResourceProfile: tier=%s mem=%.1fGB cores=%d recursion_default=%d timeout_default=%ds workspace_timeout=%ds workspace_recursion=%d",
        profile.tier,
        profile.total_mem_gb,
        profile.cpu_cores,
        profile.recursion_default,
        profile.timeout_default_s,
        profile.workspace_timeout_s,
        profile.workspace_recursion_default,
    )
    return profile


_PROFILE: ResourceProfile | None = None


def get_resource_profile() -> ResourceProfile:
    """Singleton accessor — evaluated once per process at first call."""
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = _compute_profile()
    return _PROFILE
