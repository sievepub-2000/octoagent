"""Skill version registry — tracks all skill versions and their lineage.

Stores versions in a lightweight JSON file alongside the skill directory tree.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.storage.skill_evolution.types import EvolutionMode, EvolutionRecord, QualityMetrics, SkillVersion

logger = logging.getLogger(__name__)

_REGISTRY_FILE = "skill_evolution_registry.json"


class SkillEvolutionRegistry:
    """In-memory registry backed by a JSON file."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # blockbuster raises BlockingError when mkdir is called inside
            # an async event loop.  Safe to ignore — the directory either
            # already exists or will be created lazily on first write.
            pass
        self._path = self._data_dir / _REGISTRY_FILE
        self._versions: dict[str, list[SkillVersion]] = {}
        self._records: list[EvolutionRecord] = []
        self._metrics: dict[str, QualityMetrics] = {}
        self._load()

    # ------------------------------------------------------------------ I/O

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
            for name, versions in raw.get("versions", {}).items():
                self._versions[name] = [SkillVersion(**v) for v in versions]
            self._records = [EvolutionRecord(**r) for r in raw.get("records", [])]
            self._metrics = {k: QualityMetrics(**v) for k, v in raw.get("metrics", {}).items()}
        except Exception:
            logger.warning("Failed to load evolution registry; starting fresh", exc_info=True)

    def save(self) -> None:
        payload: dict[str, Any] = {
            "versions": {k: [v.model_dump(mode="json") for v in vs] for k, vs in self._versions.items()},
            "records": [r.model_dump(mode="json") for r in self._records],
            "metrics": {k: v.model_dump(mode="json") for k, v in self._metrics.items()},
        }
        try:
            self._path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        except Exception:
            logger.warning("Failed to persist evolution registry (blocking context?)", exc_info=True)

    # -------------------------------------------------------------- Versions

    def register_skill(self, name: str) -> SkillVersion:
        """Ensure *name* has at least v1 in the registry."""
        versions = self._versions.setdefault(name, [])
        if not versions:
            v = SkillVersion(skill_name=name, version=1)
            versions.append(v)
            self.save()
        return versions[-1]

    def latest_version(self, name: str) -> SkillVersion | None:
        versions = self._versions.get(name)
        return versions[-1] if versions else None

    def add_version(
        self,
        name: str,
        mode: EvolutionMode,
        *,
        parent_name: str | None = None,
        parent_version: int | None = None,
        diff_summary: str = "",
        reason: str = "",
    ) -> SkillVersion:
        current = self.latest_version(name)
        next_ver = (current.version + 1) if current else 1
        sv = SkillVersion(
            skill_name=name,
            version=next_ver,
            parent_name=parent_name or name,
            parent_version=parent_version or (current.version if current else None),
            mode=mode,
            diff_summary=diff_summary,
        )
        self._versions.setdefault(name, []).append(sv)

        rec = EvolutionRecord(
            id=f"{name}@v{next_ver}",
            skill_name=name,
            from_version=sv.parent_version or 0,
            to_version=next_ver,
            mode=mode,
            reason=reason,
            diff_summary=diff_summary,
        )
        self._records.append(rec)
        self.save()
        return sv

    def list_versions(self, name: str) -> list[SkillVersion]:
        return list(self._versions.get(name, []))

    def list_all_skills(self) -> list[str]:
        return list(self._versions.keys())

    # --------------------------------------------------------------- Records

    def list_records(self, limit: int = 50) -> list[EvolutionRecord]:
        return list(reversed(self._records[-limit:]))

    # --------------------------------------------------------------- Metrics

    def get_metrics(self, name: str) -> QualityMetrics:
        if name not in self._metrics:
            self._metrics[name] = QualityMetrics(skill_name=name)
        return self._metrics[name]

    def record_execution(self, name: str, *, success: bool, latency_ms: float = 0.0) -> None:
        m = self.get_metrics(name)
        m.applied_count += 1
        if success:
            m.success_count += 1
        else:
            m.failure_count += 1
        # Running average
        total = m.success_count + m.failure_count
        m.avg_latency_ms = ((m.avg_latency_ms * (total - 1)) + latency_ms) / total if total else 0.0
        m.last_used = datetime.utcnow()
        self.save()

    def all_metrics(self) -> list[QualityMetrics]:
        return list(self._metrics.values())
