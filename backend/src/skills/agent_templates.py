from __future__ import annotations

import io
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from src.skills.types import Skill
from src.utils.json_atomic import write_json_atomic

AGENT_TEMPLATE_FILE_NAME = "agent-templates.json"
AGENCY_AGENTS_SKILL_NAME = "agency-agents"
AGENCY_AGENTS_SOURCE_REPO = "itallstartedwithaidea/agency-agents"
AGENCY_AGENTS_DOWNLOAD_URL = (
    "https://codeload.github.com/itallstartedwithaidea/agency-agents/zip/refs/heads/main"
)

_AGENCY_AGENT_DIRS = (
    "design",
    "engineering",
    "marketing",
    "product",
    "project-management",
    "testing",
    "support",
    "spatial-computing",
    "specialized",
    "strategy",
)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return slug or "agent-template"


def _extract_markdown_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(markdown)
    if not match:
        return {}, markdown.strip()
    frontmatter = yaml.safe_load(match.group(1)) or {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return frontmatter, match.group(2).strip()


def _extract_repo_root_from_archive(temp_root: Path) -> Path:
    extracted_items = [item for item in temp_root.iterdir() if item.name != "__MACOSX"]
    if len(extracted_items) == 1 and extracted_items[0].is_dir():
        return extracted_items[0]
    return temp_root


def _parse_agency_agent_markdown(file_path: Path, category: str) -> dict[str, Any] | None:
    markdown = file_path.read_text(encoding="utf-8")
    frontmatter, body = _extract_markdown_frontmatter(markdown)
    name = str(frontmatter.get("name", "")).strip()
    description = str(frontmatter.get("description", "")).strip()
    if not name or not description or not body:
        return None

    return {
        "template_id": _slugify(name),
        "name": name,
        "description": description,
        "source_category": category,
        "source_path": f"{category}/{file_path.name}",
        "color": str(frontmatter.get("color", "")).strip() or None,
        "model": None,
        "tool_groups": None,
        "soul": body,
    }


def _ensure_unique_template_ids(templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    for template in templates:
        base_id = str(template["template_id"])
        next_index = seen.get(base_id, 0)
        if next_index == 0:
            seen[base_id] = 1
            continue
        next_index += 1
        seen[base_id] = next_index
        template["template_id"] = f"{base_id}-{next_index}"
    return templates


def parse_agency_agents_repo(repo_root: Path) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    for category in _AGENCY_AGENT_DIRS:
        category_dir = repo_root / category
        if not category_dir.exists() or not category_dir.is_dir():
            continue
        for file_path in sorted(category_dir.glob("*.md")):
            template = _parse_agency_agent_markdown(file_path, category)
            if template is not None:
                templates.append(template)
    return _ensure_unique_template_ids(templates)


def write_agency_agents_skill(skill_dir: Path, templates: list[dict[str, Any]]) -> None:
    installed_at = datetime.now(UTC).isoformat()
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_markdown = "\n".join(
        [
            "---",
            f"name: {AGENCY_AGENTS_SKILL_NAME}",
            "description: Upstream Agency Agents library converted into OctoAgent agent templates.",
            "license: MIT",
            "---",
            "",
            "This skill is generated from the upstream Agency Agents project and provides",
            "agent templates for OctoAgent custom agent creation.",
            "",
            f"- Source repo: {AGENCY_AGENTS_SOURCE_REPO}",
            f"- Installed at: {installed_at}",
            f"- Template count: {len(templates)}",
            "",
            "Use the agent creation page to select one of these templates and bootstrap a",
            "custom agent with the upstream personality, workflow, and deliverables.",
            "",
        ]
    )
    (skill_dir / "SKILL.md").write_text(skill_markdown, encoding="utf-8")

    payload = {
        "version": 1,
        "source": {
            "kind": "agency-agents",
            "repo": AGENCY_AGENTS_SOURCE_REPO,
            "download_url": AGENCY_AGENTS_DOWNLOAD_URL,
            "installed_at": installed_at,
        },
        "templates": templates,
    }
    write_json_atomic(skill_dir / AGENT_TEMPLATE_FILE_NAME, payload)


def install_agency_agents_skill_from_archive(
    archive_bytes: bytes,
    custom_skills_dir: Path,
    *,
    overwrite: bool = True,
) -> tuple[str, int]:
    temp_root = custom_skills_dir / ".agency-agents-tmp"
    if temp_root.exists():
        for child in temp_root.iterdir():
            if child.is_dir():
                import shutil

                shutil.rmtree(child)
            else:
                child.unlink()
    temp_root.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            for member in archive.infolist():
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError(f"Unsafe path in Agency Agents archive: {member.filename}")
            archive.extractall(temp_root)

        repo_root = _extract_repo_root_from_archive(temp_root)
        templates = parse_agency_agents_repo(repo_root)
        if not templates:
            raise ValueError("Agency Agents archive did not contain any parseable agent templates")

        target_dir = custom_skills_dir / AGENCY_AGENTS_SKILL_NAME
        if target_dir.exists():
            if not overwrite:
                raise FileExistsError(f"Skill '{AGENCY_AGENTS_SKILL_NAME}' already exists")
            import shutil

            shutil.rmtree(target_dir)

        write_agency_agents_skill(target_dir, templates)
        return AGENCY_AGENTS_SKILL_NAME, len(templates)
    finally:
        if temp_root.exists():
            import shutil

            shutil.rmtree(temp_root)


def _load_skill_templates_payload(skill_dir: Path) -> dict[str, Any] | None:
    payload_path = skill_dir / AGENT_TEMPLATE_FILE_NAME
    if not payload_path.exists():
        return None
    try:
        import json

        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    templates = payload.get("templates")
    if not isinstance(templates, list):
        return None
    return payload


def list_agent_template_summaries(skills: list[Skill]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for skill in skills:
        payload = _load_skill_templates_payload(skill.skill_dir)
        if payload is None:
            continue
        for template in payload.get("templates", []):
            if not isinstance(template, dict):
                continue
            summaries.append(
                {
                    "skill_name": skill.name,
                    "skill_enabled": skill.enabled,
                    "template_id": str(template.get("template_id", "")).strip(),
                    "name": str(template.get("name", "")).strip(),
                    "description": str(template.get("description", "")).strip(),
                    "source_category": template.get("source_category"),
                    "source_path": template.get("source_path"),
                    "color": template.get("color"),
                }
            )
    return [entry for entry in summaries if entry["template_id"] and entry["name"]]


def load_agent_template_detail(skills: list[Skill], skill_name: str, template_id: str) -> dict[str, Any] | None:
    skill = next((item for item in skills if item.name == skill_name), None)
    if skill is None:
        return None
    payload = _load_skill_templates_payload(skill.skill_dir)
    if payload is None:
        return None
    for template in payload.get("templates", []):
        if not isinstance(template, dict):
            continue
        if str(template.get("template_id", "")).strip() != template_id:
            continue
        return {
            "skill_name": skill.name,
            "skill_enabled": skill.enabled,
            "template_id": template_id,
            "name": str(template.get("name", "")).strip(),
            "description": str(template.get("description", "")).strip(),
            "source_category": template.get("source_category"),
            "source_path": template.get("source_path"),
            "color": template.get("color"),
            "model": template.get("model"),
            "tool_groups": template.get("tool_groups"),
            "soul": str(template.get("soul", "")).strip(),
        }
    return None