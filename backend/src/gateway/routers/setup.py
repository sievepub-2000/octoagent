"""Setup router — workspace initialization and system configuration.

Provides endpoints for the first-run setup wizard to validate workspace paths,
apply configuration, and verify system readiness.
"""

import asyncio
import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.config import get_app_config, get_paths
from src.config.paths import get_setup_state_file
from src.skills.loader import load_skills

router = APIRouter(prefix="/api/setup", tags=["setup"])

logger = logging.getLogger(__name__)


def _langgraph_healthcheck_url() -> str:
    configured_base_url = os.getenv("OCTO_LANGGRAPH_BASE_URL", "").strip()
    if configured_base_url:
        return f"{configured_base_url.rstrip('/')}/ok"
    port = os.getenv("OCTO_LANGGRAPH_PORT", "19884").strip() or "19884"
    return f"http://127.0.0.1:{port}/ok"


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ValidateWorkspaceRequest(BaseModel):
    """Validate whether a workspace path can be used."""
    path: str = Field(..., description="Filesystem path to validate", max_length=4096)


class ValidateWorkspaceResponse(BaseModel):
    valid: bool
    resolved_path: str = ""
    exists: bool = False
    writable: bool = False
    free_space_mb: int = 0
    error: str = ""


class ApplySetupRequest(BaseModel):
    """Apply initial setup configuration."""
    workspace_path: str = Field(default="", description="Root workspace path")
    default_model: str = Field(default="", description="Preferred model name")
    sandbox_mode: str = Field(default="local", description="'local' or 'docker'")


class ApplySetupResponse(BaseModel):
    success: bool
    workspace_path: str = ""
    default_model: str = ""
    sandbox_mode: str = "local"
    directories_created: list[str] = Field(default_factory=list)
    error: str = ""


class SystemStatusResponse(BaseModel):
    """System readiness check for the setup wizard."""
    workspace_ready: bool = False
    workspace_path: str = ""
    configured_default_model: str = ""
    configured_sandbox_mode: str = "local"
    models_configured: int = 0
    skills_available: int = 0
    mcp_servers: int = 0
    gateway_healthy: bool = True
    langgraph_reachable: bool = False
    embedding_backend: str = ""
    embedding_dim: int = 0


class BrowseDirectoryRequest(BaseModel):
    """Browse a directory's children for the path picker."""
    path: str = Field(default="~", description="Directory path to list children of", max_length=4096)


class DirectoryEntry(BaseModel):
    name: str
    path: str
    is_dir: bool


class BrowseDirectoryResponse(BaseModel):
    resolved_path: str = ""
    parent: str = ""
    entries: list[DirectoryEntry] = Field(default_factory=list)
    error: str = ""


class CreateDirectoryRequest(BaseModel):
    """Create a new directory."""
    path: str = Field(..., description="Full path of the directory to create", max_length=4096)


class CreateDirectoryResponse(BaseModel):
    success: bool = False
    resolved_path: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_path(raw: str) -> Path:
    """Expand ~ and resolve to absolute path.

    NOTE: We intentionally do NOT expand environment variables ($HOME, etc.)
    to prevent information disclosure of server-side env vars.
    """
    expanded = os.path.expanduser(raw.strip())
    return Path(expanded).resolve()


# Paths that are safe roots for workspace operations.
# Only paths under these prefixes (or the configured workspace) are allowed.
_SAFE_ROOTS = [
    Path("/home"),
    Path("/tmp"),
    Path("/opt"),
    Path("/var/lib"),
    Path("/srv"),
]


def _is_safe_path(resolved: Path) -> bool:
    """Check whether *resolved* is under an allowed root directory.

    Uses ``Path.is_relative_to`` (Python 3.9+) to block all system paths
    instead of a fragile exact-match blocklist.
    """
    # Always allow the configured workspace base dir
    try:
        base = get_paths().base_dir.resolve()
        if resolved == base or resolved.is_relative_to(base):
            return True
    except Exception:
        pass

    return any(resolved == root or resolved.is_relative_to(root) for root in _SAFE_ROOTS)


def _check_writable(p: Path) -> bool:
    """Check if the path (or its closest existing ancestor) is writable."""
    target = p
    while not target.exists():
        target = target.parent
        if target == target.parent:
            return False
    return os.access(target, os.W_OK)


def _free_space_mb(p: Path) -> int:
    """Return available disk space in MB for the path's mount point."""
    target = p
    while not target.exists():
        target = target.parent
    try:
        usage = shutil.disk_usage(target)
        return int(usage.free / (1024 * 1024))
    except OSError:
        return 0


def _setup_state_file() -> Path:
    return get_setup_state_file()


def _load_setup_state() -> dict[str, str]:
    target = _setup_state_file()
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(key): str(value) for key, value in data.items()}
    except Exception:
        logger.warning("Failed to load setup state from %s", target, exc_info=True)
    return {}


def _save_setup_state(*, workspace_path: str, default_model: str, sandbox_mode: str) -> None:
    target = _setup_state_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "workspace_path": workspace_path,
                "default_model": default_model,
                "sandbox_mode": sandbox_mode,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _embedding_runtime_hint() -> tuple[str, int]:
    """Return embedding status without eagerly initializing heavy models."""
    try:
        from src.models.embedding_service import get_embedding_service

        service = get_embedding_service()
        backend = getattr(service, "_backend", None)
        if backend is None:
            return "lazy", 0
        return type(backend).__name__, int(getattr(backend, "dim", 0) or 0)
    except Exception:
        return "unavailable", 0


def _save_workspace_env_state(
    workspace_root: Path,
    *,
    default_model: str,
    sandbox_mode: str,
    directories_created: list[str],
) -> None:
    env_dir = workspace_root / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    setup_snapshot = {
        "workspace_path": str(workspace_root),
        "default_model": default_model,
        "sandbox_mode": sandbox_mode,
        "created_at": datetime.now(UTC).isoformat(),
        "layout": {
            "default_dir": str(workspace_root / "default"),
            "env_dir": str(env_dir),
            "workflow_dir": str(workspace_root / "workflow"),
            "taskwork_dir": str(workspace_root / "workflow" / "taskwork"),
        },
        "directories_created": directories_created,
    }
    (env_dir / "setup.json").write_text(
        json.dumps(setup_snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/validate-workspace",
    response_model=ValidateWorkspaceResponse,
    summary="Validate a workspace path",
)
async def validate_workspace(req: ValidateWorkspaceRequest) -> ValidateWorkspaceResponse:
    """Check whether a workspace path is valid, writable, and has enough space."""
    if not req.path.strip():
        return ValidateWorkspaceResponse(valid=False, error="Path cannot be empty")

    try:
        resolved = _resolve_path(req.path)
    except Exception as e:
        return ValidateWorkspaceResponse(valid=False, error=f"Invalid path: {e}")

    # Only allow paths under safe root directories
    if not _is_safe_path(resolved):
        return ValidateWorkspaceResponse(
            valid=False,
            resolved_path=str(resolved),
            error="Path is outside allowed directories. Use a path under /home, /tmp, /opt, /var/lib, or /srv.",
        )

    exists = resolved.exists()
    writable = _check_writable(resolved)
    free_mb = _free_space_mb(resolved)

    if not writable:
        return ValidateWorkspaceResponse(
            valid=False,
            resolved_path=str(resolved),
            exists=exists,
            writable=False,
            free_space_mb=free_mb,
            error="Path is not writable. Check permissions.",
        )

    if free_mb < 100:
        return ValidateWorkspaceResponse(
            valid=False,
            resolved_path=str(resolved),
            exists=exists,
            writable=writable,
            free_space_mb=free_mb,
            error="Less than 100 MB free disk space",
        )

    return ValidateWorkspaceResponse(
        valid=True,
        resolved_path=str(resolved),
        exists=exists,
        writable=True,
        free_space_mb=free_mb,
    )


@router.post(
    "/apply",
    response_model=ApplySetupResponse,
    summary="Apply initial setup configuration",
)
async def apply_setup(req: ApplySetupRequest) -> ApplySetupResponse:
    """Create workspace directories and persist configuration."""
    workspace = req.workspace_path.strip()
    if not workspace:
        # Use the default backend path
        workspace = str(get_paths().base_dir)

    try:
        resolved = _resolve_path(workspace)
    except Exception as e:
        return ApplySetupResponse(success=False, error=f"Invalid path: {e}")

    if not _is_safe_path(resolved):
        return ApplySetupResponse(
            success=False,
            error="Path is outside allowed directories. Use a path under /home, /tmp, /opt, /var/lib, or /srv.",
        )

    # Create core directory structure
    dirs_to_create = [
        resolved,
        resolved / "default",
        resolved / "default" / "agents",
        resolved / "default" / "threads",
        resolved / "default" / "code",
        resolved / "env",
        resolved / "workflow",
        resolved / "workflow" / "taskwork",
        resolved / "workflow" / "taskwork" / "_state",
        resolved / "runtime",
        resolved / "runtime" / "browser_runtime",
        resolved / "runtime" / "channels",
        resolved / "runtime" / "plugins",
        resolved / "runtime" / "system_execution",
    ]

    created: list[str] = []
    try:
        for d in dirs_to_create:
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                created.append(str(d))
    except PermissionError:
        return ApplySetupResponse(
            success=False,
            workspace_path=str(resolved),
            error="Permission denied when creating directories",
        )
    except OSError as e:
        return ApplySetupResponse(
            success=False,
            workspace_path=str(resolved),
            error=f"Failed to create directories: {e}",
        )

    # Initialize memory.json if not present
    memory_file = resolved / "default" / "memory.json"
    if not memory_file.exists():
        try:
            memory_file.write_text('{"user_context": "", "facts": [], "history": []}')
        except OSError:
            pass

    # Initialize USER.md if not present
    user_md = resolved / "default" / "USER.md"
    if not user_md.exists():
        try:
            user_md.write_text("# User Profile\n\nAdd your preferences and context here.\n")
        except OSError:
            pass

    try:
        _save_setup_state(
            workspace_path=str(resolved),
            default_model=req.default_model,
            sandbox_mode=req.sandbox_mode,
        )
        _save_workspace_env_state(
            resolved,
            default_model=req.default_model,
            sandbox_mode=req.sandbox_mode,
            directories_created=created,
        )
    except OSError:
        logger.warning("Failed to persist setup state for workspace=%s", resolved, exc_info=True)

    logger.info("Setup applied: workspace=%s, model=%s, sandbox=%s", resolved, req.default_model, req.sandbox_mode)

    return ApplySetupResponse(
        success=True,
        workspace_path=str(resolved),
        default_model=req.default_model,
        sandbox_mode=req.sandbox_mode,
        directories_created=created,
    )


@router.post(
    "/browse-directory",
    response_model=BrowseDirectoryResponse,
    summary="Browse directory children for the path picker",
)
async def browse_directory(req: BrowseDirectoryRequest) -> BrowseDirectoryResponse:
    """List immediate child directories (and files) for a path picker UI."""
    raw = req.path.strip() or "~"
    try:
        resolved = _resolve_path(raw)
    except Exception as e:
        return BrowseDirectoryResponse(error=f"Invalid path: {e}")

    # Restrict browsing to safe root directories
    if not _is_safe_path(resolved):
        return BrowseDirectoryResponse(
            resolved_path=str(resolved),
            error="Cannot browse outside allowed directories.",
        )

    if not resolved.exists():
        return BrowseDirectoryResponse(
            resolved_path=str(resolved),
            parent=str(resolved.parent),
            error="Directory does not exist",
        )

    if not resolved.is_dir():
        return BrowseDirectoryResponse(
            resolved_path=str(resolved),
            parent=str(resolved.parent),
            error="Path is not a directory",
        )

    entries: list[DirectoryEntry] = []
    try:
        for child in sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            # Skip hidden files/dirs and system dirs
            if child.name.startswith("."):
                continue
            entries.append(DirectoryEntry(
                name=child.name,
                path=str(child),
                is_dir=child.is_dir(),
            ))
    except PermissionError:
        return BrowseDirectoryResponse(
            resolved_path=str(resolved),
            parent=str(resolved.parent),
            error="Permission denied",
        )
    except OSError as e:
        return BrowseDirectoryResponse(
            resolved_path=str(resolved),
            parent=str(resolved.parent),
            error=str(e),
        )

    # Cap to 200 entries to prevent huge responses
    return BrowseDirectoryResponse(
        resolved_path=str(resolved),
        parent=str(resolved.parent) if resolved != resolved.parent else "",
        entries=entries[:200],
    )


@router.post(
    "/create-directory",
    response_model=CreateDirectoryResponse,
    summary="Create a new directory for the path picker",
)
async def create_directory(req: CreateDirectoryRequest) -> CreateDirectoryResponse:
    """Create a new directory. Used by the directory browser's 'new folder' feature."""
    raw = req.path.strip()
    if not raw:
        return CreateDirectoryResponse(error="Path cannot be empty")

    try:
        resolved = _resolve_path(raw)
    except Exception as e:
        return CreateDirectoryResponse(error=f"Invalid path: {e}")

    # Only allow paths under safe root directories
    if not _is_safe_path(resolved):
        return CreateDirectoryResponse(
            resolved_path=str(resolved),
            error="Path is outside allowed directories. Use a path under /home, /tmp, /opt, /var/lib, or /srv.",
        )

    if resolved.exists():
        return CreateDirectoryResponse(
            success=True,
            resolved_path=str(resolved),
        )

    try:
        resolved.mkdir(parents=True, exist_ok=True)
        return CreateDirectoryResponse(
            success=True,
            resolved_path=str(resolved),
        )
    except PermissionError:
        return CreateDirectoryResponse(
            resolved_path=str(resolved),
            error="Permission denied",
        )
    except OSError as e:
        return CreateDirectoryResponse(
            resolved_path=str(resolved),
            error=str(e),
        )


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    summary="System readiness status for setup wizard",
)
async def get_system_status() -> SystemStatusResponse:
    """Return a summary of system readiness for the setup wizard."""
    paths = get_paths()
    default_workspace_dir = getattr(paths, "default_workspace_dir", paths.base_dir / "default")
    env_dir = getattr(paths, "env_dir", paths.base_dir / "env")
    workflow_tasks_dir = getattr(paths, "workflow_tasks_dir", paths.base_dir / "workflow" / "taskwork")
    workspace_exists = all(directory.exists() for directory in [default_workspace_dir, env_dir, workflow_tasks_dir])

    # Count configured models
    try:
        config = get_app_config()
        models_count = len(config.models) if config.models else 0
    except Exception:
        models_count = 0

    # Count available skills
    skills_count = 0
    try:
        skills_count = len(await asyncio.to_thread(load_skills, None, True, False))
    except Exception:
        pass

    # Count MCP servers
    mcp_count = 0
    try:
        from src.config.extensions_config import ExtensionsConfig
        ext_config = ExtensionsConfig.from_file()
        mcp_count = len(ext_config.get_enabled_mcp_servers())
    except Exception:
        pass

    # Check LangGraph reachability
    langgraph_reachable = False
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(_langgraph_healthcheck_url(), timeout=2)
            langgraph_reachable = resp.status_code == 200
    except Exception:
        pass

    embedding_backend, embedding_dim = _embedding_runtime_hint()

    setup_state = _load_setup_state()

    return SystemStatusResponse(
        workspace_ready=workspace_exists,
        workspace_path=setup_state.get("workspace_path") or str(paths.base_dir),
        configured_default_model=setup_state.get("default_model", ""),
        configured_sandbox_mode=setup_state.get("sandbox_mode", "local"),
        models_configured=models_count,
        skills_available=skills_count,
        mcp_servers=mcp_count,
        gateway_healthy=True,
        langgraph_reachable=langgraph_reachable,
        embedding_backend=embedding_backend,
        embedding_dim=embedding_dim,
    )
