"""Configuration and loaders for custom agents."""

import logging
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from src.runtime.config.paths import get_paths

logger = logging.getLogger(__name__)

SOUL_FILENAME = "SOUL.md"
AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")


class AgentConfig(BaseModel):
    """Configuration for a custom agent."""

    name: str
    description: str = ""
    model: str | None = None
    tool_groups: list[str] | None = None
    avatar: str | None = None


def load_agent_config(name: str | None) -> AgentConfig | None:
    """Load the custom or default agent's config from its directory.

    Args:
        name: The agent name.

    Returns:
        AgentConfig instance.

    Raises:
        FileNotFoundError: If the agent directory or config.yaml does not exist.
        ValueError: If config.yaml cannot be parsed.
    """

    if name is None or not str(name).strip() or str(name).strip().lower() == "default":
        return None

    if not AGENT_NAME_PATTERN.match(name):
        raise ValueError(f"Invalid agent name '{name}'. Must match pattern: {AGENT_NAME_PATTERN.pattern}")
    agent_dir = get_paths().agent_dir(name)
    config_file = agent_dir / "config.yaml"

    if not agent_dir.exists():
        raise FileNotFoundError(f"Agent directory not found: {agent_dir}")

    if config_file.exists():
        try:
            with open(config_file, encoding="utf-8") as f:
                data: dict[str, Any] = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse agent config {config_file}: {e}") from e
    else:
        # Tolerant fallback: agents may be stored with only SOUL.md.
        # Synthesize a minimal config from the directory name and first SOUL line.
        data: dict[str, Any] = {}
        soul_path = agent_dir / SOUL_FILENAME
        if soul_path.exists():
            try:
                first_line = soul_path.read_text(encoding="utf-8").strip().splitlines()[0] if soul_path.stat().st_size > 0 else ""
                if first_line and first_line.startswith("#"):
                    data["description"] = first_line.lstrip("#").strip()
                elif first_line:
                    data["description"] = first_line[:200]
            except OSError:
                pass

    # Ensure name is set from directory name if not in file
    if "name" not in data:
        data["name"] = name

    # Strip unknown fields before passing to Pydantic (e.g. legacy prompt_file)
    known_fields = set(AgentConfig.model_fields.keys())
    data = {k: v for k, v in data.items() if k in known_fields}

    return AgentConfig(**data)


def load_agent_soul(agent_name: str | None) -> str | None:
    """Read the SOUL.md file for a custom agent, if it exists.

    SOUL.md defines the agent's personality, values, and behavioral guardrails.
    It is injected into the lead agent's system prompt as additional context.

    Args:
        agent_name: The name of the agent or None for the default agent.

    Returns:
        The SOUL.md content as a string, or None if the file does not exist.
    """
    agent_dir = get_paths().agent_dir(agent_name) if agent_name else get_paths().base_dir
    soul_path = agent_dir / SOUL_FILENAME
    if not soul_path.exists():
        return None
    content = soul_path.read_text(encoding="utf-8").strip()
    return content or None


def list_custom_agents() -> list[AgentConfig]:
    """Scan the agents directory and return all valid custom agents.

    Returns:
        List of AgentConfig for each valid agent directory found.
    """
    agents_dir = get_paths().agents_dir

    if not agents_dir.exists():
        return []

    agents: list[AgentConfig] = []

    for entry in sorted(agents_dir.iterdir()):
        if not entry.is_dir():
            continue

        config_file = entry / "config.yaml"
        soul_file = entry / SOUL_FILENAME
        if not config_file.exists() and not soul_file.exists():
            logger.debug(f"Skipping {entry.name}: no config.yaml or SOUL.md")
            continue

        try:
            agent_cfg = load_agent_config(entry.name)
            agents.append(agent_cfg)
        except Exception as e:
            logger.warning(f"Skipping agent '{entry.name}': {e}")

    return agents


# ---------------------------------------------------------------------------
# System agents — single-file Microsoft-style .agent.md definitions discovered
# under .github/agents/. These are read-only (editable=False, deletable=False)
# and serve as a system-provided catalogue.
# ---------------------------------------------------------------------------


_SYSTEM_AGENT_NAME_SANITIZE = re.compile(r"[^A-Za-z0-9-]+")


def _slug_from_agent_filename(stem: str) -> str:
    """Derive a deterministic slug for a system agent from its .agent.md stem."""
    return _SYSTEM_AGENT_NAME_SANITIZE.sub("-", stem.strip().lower()).strip("-")


def _system_agents_root() -> Path:
    """Return the .github/agents directory for the repository, if it exists."""
    # backend/src/config/agents_config.py -> parents[3] == repo root
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / ".github" / "agents",
        Path.cwd() / ".github" / "agents",
    ]
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_dir():
                return candidate.resolve()
        except OSError:
            continue
    return repo_root / ".github" / "agents"  # non-existent path; callers guard


def _parse_agent_md(path: Path) -> tuple[dict[str, Any], str] | None:
    """Parse a .agent.md file into (frontmatter, body).

    Returns None when frontmatter is missing or malformed.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not match:
        return None
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict):
        return None
    body = match.group(2) or ""
    return meta, body


def list_system_agents() -> list[AgentConfig]:
    """Discover single-file system agents stored under .github/agents/."""
    root = _system_agents_root()
    if not root.exists():
        return []

    agents: list[AgentConfig] = []
    for path in sorted(root.glob("*.agent.md")):
        parsed = _parse_agent_md(path)
        if parsed is None:
            logger.debug("Skipping malformed system agent file: %s", path)
            continue
        meta, _body = parsed
        raw_name = str(meta.get("name") or path.stem.replace(".agent", "")).strip()
        slug = _slug_from_agent_filename(path.stem.replace(".agent", ""))
        if not slug or not AGENT_NAME_PATTERN.match(slug):
            logger.debug("Skipping system agent with invalid slug: %s", path)
            continue
        description = str(meta.get("description") or raw_name).strip()
        try:
            agents.append(
                AgentConfig(
                    name=slug,
                    description=description[:1000],
                    model=None,
                    tool_groups=None,
                    avatar=None,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to materialize system agent %s: %s", path, exc)
    return agents


def load_system_agent(name: str) -> tuple[AgentConfig, str] | None:
    """Load a system agent by slug, returning (config, body) or None."""
    if not name or not AGENT_NAME_PATTERN.match(name):
        return None
    root = _system_agents_root()
    if not root.exists():
        return None
    target_slug = _slug_from_agent_filename(name)
    for path in root.glob("*.agent.md"):
        if _slug_from_agent_filename(path.stem.replace(".agent", "")) != target_slug:
            continue
        parsed = _parse_agent_md(path)
        if parsed is None:
            return None
        meta, body = parsed
        raw_name = str(meta.get("name") or target_slug).strip()
        description = str(meta.get("description") or raw_name).strip()
        try:
            cfg = AgentConfig(
                name=target_slug,
                description=description[:1000],
                model=None,
                tool_groups=None,
                avatar=None,
            )
        except Exception:
            return None
        return cfg, body
    return None
