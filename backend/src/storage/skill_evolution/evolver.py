"""Skill evolver — applies FIX / DERIVED / CAPTURED evolution to skill files.

All evolution is diff-based and version-tracked. Safeguards prevent runaway
cycles and prompt-injection in evolved content.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from src.storage.skill_evolution.analyzer import AnalysisSuggestion
from src.storage.skill_evolution.registry import SkillEvolutionRegistry
from src.storage.skill_evolution.types import EvolutionConfig, EvolutionMode

logger = logging.getLogger(__name__)

# Anti-loop: max evolutions per skill in a given window
_MAX_EVOLUTIONS_PER_SKILL = 5


class SkillEvolver:
    """Applies evolution suggestions to skill directories."""

    def __init__(self, registry: SkillEvolutionRegistry, skills_root: Path, config: EvolutionConfig) -> None:
        self._registry = registry
        self._skills_root = skills_root
        self._config = config
        self._recent_evolutions: dict[str, int] = {}

    def evolve(self, suggestion: AnalysisSuggestion) -> bool:
        """Apply a single evolution suggestion. Returns True on success."""
        if not self._config.enabled:
            return False

        name = suggestion.skill_name
        mode = suggestion.mode

        # Check mode-specific toggles
        if mode == EvolutionMode.FIX and not self._config.auto_fix:
            return False
        if mode == EvolutionMode.DERIVED and not self._config.auto_derive:
            return False
        if mode == EvolutionMode.CAPTURED and not self._config.auto_capture:
            return False

        # Anti-loop guard
        count = self._recent_evolutions.get(name, 0)
        if count >= _MAX_EVOLUTIONS_PER_SKILL:
            logger.warning("Anti-loop: skipping evolution for '%s' (hit %d limit)", name, _MAX_EVOLUTIONS_PER_SKILL)
            return False

        # Safety: reject content with obvious injection patterns
        if _has_injection_risk(suggestion.reason):
            logger.warning("Blocked evolution for '%s': injection risk detected in reason", name)
            return False

        try:
            if mode == EvolutionMode.FIX:
                self._apply_fix(name, suggestion)
            elif mode == EvolutionMode.DERIVED:
                self._apply_derived(name, suggestion)
            elif mode == EvolutionMode.CAPTURED:
                self._apply_captured(name, suggestion)
            else:
                return False

            self._recent_evolutions[name] = count + 1
            return True
        except Exception:
            logger.exception("Failed to evolve skill '%s'", name)
            return False

    # ----------------------------------------------------------------- modes

    def _apply_fix(self, name: str, suggestion: AnalysisSuggestion) -> None:
        """In-place repair of a skill's SKILL.md."""
        skill_dir = self._skills_root / name
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            logger.warning("Cannot FIX '%s': SKILL.md not found", name)
            return

        content = skill_md.read_text(encoding="utf-8")
        # Append a fix note block to the skill
        fix_block = f"\n\n<!-- evolution:fix -->\n<!-- reason: {_sanitize(suggestion.reason)} -->\n"
        skill_md.write_text(content + fix_block, encoding="utf-8")

        self._registry.add_version(
            name,
            EvolutionMode.FIX,
            diff_summary=f"Fixed: {suggestion.reason[:120]}",
            reason=suggestion.reason,
        )
        logger.info("Applied FIX evolution to '%s'", name)

    def _apply_derived(self, name: str, suggestion: AnalysisSuggestion) -> None:
        """Create a derived copy of an existing skill."""
        src_dir = self._skills_root / name
        if not src_dir.exists():
            logger.warning("Cannot DERIVE from '%s': directory not found", name)
            return

        parent_ver = self._registry.latest_version(name)
        derived_name = f"{name}-derived-v{(parent_ver.version + 1) if parent_ver else 2}"
        dest_dir = self._skills_root / derived_name

        if dest_dir.exists():
            logger.warning("Derived skill '%s' already exists — skipping", derived_name)
            return

        shutil.copytree(src_dir, dest_dir)

        self._registry.register_skill(derived_name)
        self._registry.add_version(
            derived_name,
            EvolutionMode.DERIVED,
            parent_name=name,
            parent_version=parent_ver.version if parent_ver else 1,
            diff_summary=f"Derived from {name}: {suggestion.reason[:120]}",
            reason=suggestion.reason,
        )
        logger.info("Created DERIVED skill '%s' from '%s'", derived_name, name)

    def _apply_captured(self, name: str, suggestion: AnalysisSuggestion) -> None:
        """Create a brand-new skill from a captured execution pattern."""
        skill_dir = self._skills_root / name
        if skill_dir.exists():
            logger.warning("Captured skill '%s' already exists — skipping", name)
            return

        try:
            skill_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.warning("Cannot create skill dir '%s' (blocking context?)", skill_dir)
            return
        skill_md = skill_dir / "SKILL.md"
        content = f"---\nname: {name}\ndescription: Auto-captured skill — {_sanitize(suggestion.reason[:100])}\n---\n\n# {name}\n\nCaptured from successful execution.\n\n**Reason:** {_sanitize(suggestion.reason)}\n"
        skill_md.write_text(content, encoding="utf-8")

        self._registry.register_skill(name)
        self._registry.add_version(
            name,
            EvolutionMode.CAPTURED,
            diff_summary=f"Captured: {suggestion.reason[:120]}",
            reason=suggestion.reason,
        )
        logger.info("Created CAPTURED skill '%s'", name)

    def reset_loop_counter(self) -> None:
        self._recent_evolutions.clear()


# ---------------------------------------------------------------- Helpers


def _sanitize(text: str) -> str:
    """Strip characters that could break YAML / Markdown boundaries."""
    return re.sub(r"[`\n\r]", " ", text).strip()


def _has_injection_risk(text: str) -> bool:
    """Heuristic check for prompt-injection patterns."""
    lowered = text.lower()
    patterns = [
        "ignore previous",
        "ignore all",
        "system prompt",
        "you are now",
        "<script",
        "javascript:",
        "eval(",
        "exec(",
    ]
    return any(p in lowered for p in patterns)
