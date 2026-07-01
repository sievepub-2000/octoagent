import asyncio
import os
import threading
import time
from pathlib import Path

from .parser import parse_skill_file
from .types import Skill

# In-memory cache so that the hot path (called from the async LangGraph event
# loop via the synchronous graph factory) never performs blocking filesystem IO
# after the first load.  The cache is refreshed when the TTL expires *or* when
# the Gateway explicitly calls ``invalidate_skills_cache()``.
_skills_cache: list[Skill] | None = None
_skills_cache_ts: float = 0.0
_SKILLS_CACHE_TTL: float = 3600.0  # seconds; long TTL — rely on invalidate_skills_cache() for freshness
_cache_lock = threading.Lock()


def _is_in_async_loop() -> bool:
    """Return ``True`` if called from inside a running asyncio event loop."""
    try:
        loop = asyncio.get_running_loop()
        return loop.is_running()
    except RuntimeError:
        return False


def invalidate_skills_cache() -> None:
    """Force the next ``load_skills()`` call to re-scan the filesystem.

    Only the timestamp is reset — the stale data is preserved so that callers
    inside an async event loop can still get a (potentially outdated) result
    without triggering blocking filesystem IO.
    """
    global _skills_cache_ts
    with _cache_lock:
        _skills_cache_ts = 0.0


def get_skills_root_path() -> Path:
    """
    Get the root path of the skills directory.

    Returns:
        Path to the skills directory (octoagent/skills)
    """
    # backend directory is current file's parent's parent's parent
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    # skills directory is sibling to backend directory
    skills_dir = backend_dir.parent / "skills"
    return skills_dir


def load_skills(skills_path: Path | None = None, use_config: bool = True, enabled_only: bool = False) -> list[Skill]:
    """
    Load all skills from the skills directory.

    Results are cached in memory for ``_SKILLS_CACHE_TTL`` seconds so that the
    synchronous graph-factory path (called from the async LangGraph event loop)
    does not trigger blocking ``os.walk`` calls after the initial scan.

    Args:
        skills_path: Optional custom path to skills directory.
                     If not provided and use_config is True, uses path from config.
                     Otherwise defaults to octoagent/skills
        use_config: Whether to load skills path from config (default: True)
        enabled_only: If True, only return enabled skills (default: False)

    Returns:
        List of Skill objects, sorted by name
    """
    global _skills_cache, _skills_cache_ts

    # Fast path: return cached result when using default args and cache is fresh
    if skills_path is None and use_config:
        with _cache_lock:
            if _skills_cache is not None and (time.monotonic() - _skills_cache_ts) < _SKILLS_CACHE_TTL:
                if enabled_only:
                    return [s for s in _skills_cache if s.enabled]
                return list(_skills_cache)

    # When called from an async event loop, filesystem operations (os.walk,
    # Path.exists, etc.) raise BlockingError via blockbuster.  Return a stale
    # cached copy instead of crashing — skills change infrequently and the
    # cache will be refreshed on the next sync-context call or server restart.
    if _is_in_async_loop():
        with _cache_lock:
            if _skills_cache is not None:
                if enabled_only:
                    return [s for s in _skills_cache if s.enabled]
                return list(_skills_cache)
        return []

    if skills_path is None:
        if use_config:
            try:
                from src.runtime.config import get_app_config

                config = get_app_config()
                skills_path = config.skills.get_skills_path()
            except Exception:
                # Fallback to default if config fails
                skills_path = get_skills_root_path()
        else:
            skills_path = get_skills_root_path()

    if not skills_path.exists():
        return []

    skills = []

    # Scan public and custom directories
    for category in ["public", "custom"]:
        category_path = skills_path / category
        if not category_path.exists() or not category_path.is_dir():
            continue

        for current_root, dir_names, file_names in os.walk(category_path):
            # Keep traversal deterministic and skip hidden directories.
            dir_names[:] = sorted(name for name in dir_names if not name.startswith("."))
            if "SKILL.md" not in file_names:
                continue

            skill_file = Path(current_root) / "SKILL.md"
            relative_path = skill_file.parent.relative_to(category_path)

            skill = parse_skill_file(skill_file, category=category, relative_path=relative_path)
            if skill:
                skills.append(skill)

    # Load skills state configuration and update enabled status
    # NOTE: We use ExtensionsConfig.from_file() instead of get_extensions_config()
    # to always read the latest configuration from disk. This ensures that changes
    # made through the Gateway API (which runs in a separate process) are immediately
    # reflected in the LangGraph Server when loading skills.
    try:
        from src.runtime.config.extensions_config import ExtensionsConfig

        extensions_config = ExtensionsConfig.from_file()
        for skill in skills:
            skill.enabled = extensions_config.is_skill_enabled(skill.name, skill.category)
    except Exception as e:
        # If config loading fails, default to all enabled
        logger.debug("Warning: Failed to load extensions config: {e}")

    # ── Extra skill roots (e.g. ``.agents/skills/`` shipped with the repo) ──
    # Loaded only if not already present (skills/public/ takes priority).
    seen_names = {s.name for s in skills}
    repo_root = Path(__file__).resolve().parents[4]
    EXTRA_SKILL_ROOTS = [
        (repo_root / ".agents" / "skills", "public"),
        (repo_root / "project_docs" / "skills" / "public", "public"),
    ]
    for extra_root, extra_category in EXTRA_SKILL_ROOTS:
        if not extra_root.exists() or not extra_root.is_dir():
            continue
        for current_root, dir_names, file_names in os.walk(extra_root):
            dir_names[:] = sorted(name for name in dir_names if not name.startswith("."))
            if "SKILL.md" not in file_names:
                continue
            skill_file = Path(current_root) / "SKILL.md"
            try:
                relative_path = skill_file.parent.relative_to(extra_root)
            except ValueError:
                continue
            skill = parse_skill_file(skill_file, category=extra_category, relative_path=relative_path)
            if skill and skill.name not in seen_names:
                skills.append(skill)
                seen_names.add(skill.name)

    # Sort by name for consistent ordering
    skills.sort(key=lambda s: s.name)

    # Populate cache when using default config path (cache ALL skills, filter later)
    if use_config:
        with _cache_lock:
            _skills_cache = list(skills)
            _skills_cache_ts = time.monotonic()

    # Filter by enabled status if requested
    if enabled_only:
        skills = [skill for skill in skills if skill.enabled]

    return skills


def _warm_cache() -> None:
    """Pre-populate the skills cache at import time so the first call from the
    async LangGraph event loop never triggers blocking filesystem IO."""
    import asyncio

    # Skip if we're being re-imported inside the running event loop (hot-reload).
    # In that case the existing cache (if any) is still valid.
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            return
    except RuntimeError:
        pass  # No event loop — safe to proceed

    try:
        load_skills()  # default args → use_config=True → populates _skills_cache
    except Exception:
        pass  # best-effort; will retry later


# Seed on import — runs before the ASGI event loop starts.
_warm_cache()
