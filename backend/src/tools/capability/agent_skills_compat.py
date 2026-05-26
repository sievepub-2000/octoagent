"""Compatibility scanner for upstream agent-skills style capability packs."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.runtime.config.extensions_config import AgentSkillsCompatConfig

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_LINKED_SKILL_RE = re.compile(r"agent-skills[:/](?P<skill>[a-z0-9-]+)")


@dataclass(frozen=True)
class AgentSkillsCompatEntry:
    """Normalized representation of an upstream agent-skills asset."""

    capability_id: str
    kind: str
    name: str
    display_name: str
    description: str
    source: str
    provides: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _looks_like_agent_skills_pack(path: Path) -> bool:
    return path.exists() and (path / "skills").exists() and (path / ".claude" / "commands").exists()


def compat_item_default_enabled(kind: str) -> bool:
    return kind in {"skill", "agent_persona", "reference"}


def compat_item_requires_trust(kind: str) -> bool:
    return kind in {"command", "hook"}


def compat_item_toggleable(kind: str) -> bool:
    return kind in {"skill", "command", "agent_persona", "reference", "hook"}


def compat_item_trust_allowed(kind: str, config: AgentSkillsCompatConfig) -> bool:
    if not compat_item_requires_trust(kind):
        return True
    return config.trust_level == "trusted"


def resolve_agent_skills_source_root(
    config: AgentSkillsCompatConfig,
    *,
    allow_disabled: bool = False,
) -> Path | None:
    """Resolve the effective upstream source root for agent-skills compatibility."""

    if not config.enabled and not allow_disabled:
        return None

    raw_path = os.getenv("OCTO_AGENT_AGENT_SKILLS_SOURCE") or config.source_root
    if raw_path:
        candidate = Path(raw_path).expanduser().resolve()
        if _looks_like_agent_skills_pack(candidate):
            return candidate

    clone_candidate = _repo_root() / "references" / "_clones" / "agent-skills"
    if _looks_like_agent_skills_pack(clone_candidate):
        return clone_candidate

    return None


def _read_with_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    payload = yaml.safe_load(match.group(1)) or {}
    if not isinstance(payload, dict):
        payload = {}
    return payload, text[match.end() :]


def _markdown_title(body: str, path: Path) -> str:
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            return line.lstrip("#").strip()
        return line
    return path.stem.replace("-", " ").replace("_", " ").strip() or path.stem


def _markdown_summary(body: str) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if line.startswith("#"):
            continue
        current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs[0] if paragraphs else ""


def _hook_summary(path: Path) -> str:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#!"):
            continue
        if line.startswith("#"):
            return line.lstrip("#").strip()
        return line[:120]
    return path.stem


def _linked_skills(body: str) -> tuple[str, ...]:
    return tuple(sorted({match.group("skill") for match in _LINKED_SKILL_RE.finditer(body)}))


def build_agent_skills_compat_entries(
    config: AgentSkillsCompatConfig,
    *,
    allow_disabled: bool = False,
) -> list[AgentSkillsCompatEntry]:
    """Scan an upstream agent-skills style pack and normalize discovered assets."""

    root = resolve_agent_skills_source_root(config, allow_disabled=allow_disabled)
    if root is None:
        return []

    items: list[AgentSkillsCompatEntry] = []

    if config.include_skills:
        for skill_md in sorted((root / "skills").glob("*/SKILL.md")):
            frontmatter, body = _read_with_frontmatter(skill_md)
            name = str(frontmatter.get("name") or skill_md.parent.name)
            description = str(frontmatter.get("description") or _markdown_summary(body))
            items.append(
                AgentSkillsCompatEntry(
                    capability_id=f"agent_skills:skill:{name}",
                    kind="skill",
                    name=name,
                    display_name=name,
                    description=description,
                    source=skill_md.relative_to(root).as_posix(),
                    provides=(f"agent-skill:{name}",),
                    metadata={
                        "compat_source_root": str(root),
                        "compat_type": "agent_skills",
                        "relative_path": skill_md.relative_to(root).as_posix(),
                    },
                )
            )

    if config.include_commands:
        for command_md in sorted((root / ".claude" / "commands").glob("**/*.md")):
            frontmatter, body = _read_with_frontmatter(command_md)
            name = command_md.stem
            description = str(frontmatter.get("description") or _markdown_summary(body))
            items.append(
                AgentSkillsCompatEntry(
                    capability_id=f"agent_skills:command:{name}",
                    kind="command",
                    name=name,
                    display_name=_markdown_title(body, command_md),
                    description=description,
                    source=command_md.relative_to(root).as_posix(),
                    provides=(f"command:{name}",),
                    metadata={
                        "compat_source_root": str(root),
                        "compat_type": "agent_skills",
                        "relative_path": command_md.relative_to(root).as_posix(),
                        "linked_skills": list(_linked_skills(body)),
                    },
                )
            )

    if config.include_agents:
        for agent_md in sorted((root / "agents").glob("*.md")):
            _, body = _read_with_frontmatter(agent_md)
            items.append(
                AgentSkillsCompatEntry(
                    capability_id=f"agent_skills:agent:{agent_md.stem}",
                    kind="agent_persona",
                    name=agent_md.stem,
                    display_name=_markdown_title(body, agent_md),
                    description=_markdown_summary(body),
                    source=agent_md.relative_to(root).as_posix(),
                    provides=(f"agent_persona:{agent_md.stem}",),
                    metadata={
                        "compat_source_root": str(root),
                        "compat_type": "agent_skills",
                        "relative_path": agent_md.relative_to(root).as_posix(),
                    },
                )
            )

    if config.include_references:
        for reference_md in sorted((root / "references").glob("**/*.md")):
            _, body = _read_with_frontmatter(reference_md)
            items.append(
                AgentSkillsCompatEntry(
                    capability_id=f"agent_skills:reference:{reference_md.stem}",
                    kind="reference",
                    name=reference_md.stem,
                    display_name=_markdown_title(body, reference_md),
                    description=_markdown_summary(body),
                    source=reference_md.relative_to(root).as_posix(),
                    provides=(f"reference:{reference_md.stem}",),
                    metadata={
                        "compat_source_root": str(root),
                        "compat_type": "agent_skills",
                        "relative_path": reference_md.relative_to(root).as_posix(),
                    },
                )
            )

    if config.include_hooks:
        for hook_script in sorted((root / "hooks").glob("**/*.sh")):
            items.append(
                AgentSkillsCompatEntry(
                    capability_id=f"agent_skills:hook:{hook_script.stem}",
                    kind="hook",
                    name=hook_script.stem,
                    display_name=hook_script.stem,
                    description=_hook_summary(hook_script),
                    source=hook_script.relative_to(root).as_posix(),
                    provides=(f"hook:{hook_script.stem}",),
                    metadata={
                        "compat_source_root": str(root),
                        "compat_type": "agent_skills",
                        "relative_path": hook_script.relative_to(root).as_posix(),
                        "executable": os.access(hook_script, os.X_OK),
                    },
                )
            )

    items.sort(key=lambda item: (item.kind, item.name))
    return items
