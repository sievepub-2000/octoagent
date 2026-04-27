"""System update router — check for updates, apply updates, manage auto-update."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system-update"])

# ---------- constants ---------------------------------------------------
_DEFAULT_REPO_OWNER = "sievepub-2000"
_DEFAULT_REPO_NAME = "octoagent"
_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # backend/src/gateway/routers -> project root
_VERSION_FILE = _PROJECT_ROOT / "backend" / "pyproject.toml"
_VERSION_RELATIVE_PATH = _VERSION_FILE.relative_to(_PROJECT_ROOT).as_posix()
_AUTO_UPDATE_CONFIG = _PROJECT_ROOT / ".octoagent_auto_update.json"
_GITHUB_REMOTE_PATTERNS = (
    re.compile(r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?/?$"),
    re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?$"),
    re.compile(r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?/?$"),
)


@dataclass(frozen=True)
class RepositoryLocation:
    owner: str
    name: str
    remote_url: str
    api_url: str


_DEFAULT_REPOSITORY = RepositoryLocation(
    owner=_DEFAULT_REPO_OWNER,
    name=_DEFAULT_REPO_NAME,
    remote_url=f"https://github.com/{_DEFAULT_REPO_OWNER}/{_DEFAULT_REPO_NAME}.git",
    api_url=f"https://api.github.com/repos/{_DEFAULT_REPO_OWNER}/{_DEFAULT_REPO_NAME}",
)

# ---------- models ------------------------------------------------------

class UpdateInfo(BaseModel):
    current_version: str
    latest_version: str
    has_update: bool
    latest_commit: str = ""
    latest_date: str = ""
    changelog: str = ""


class AutoUpdateConfig(BaseModel):
    enabled: bool = False
    check_interval_hours: int = 24
    last_check: str = ""
    repository_url: str = ""


class UpdateResult(BaseModel):
    success: bool
    message: str
    new_version: str = ""


# ---------- helpers -----------------------------------------------------

def _read_current_version() -> str:
    """Read version from pyproject.toml."""
    try:
        return _read_version_from_text(_VERSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return "unknown"


def _read_version_from_text(text: str) -> str:
    """Extract the project version from TOML content."""
    try:
        parsed = tomllib.loads(text)
        project = parsed.get("project", {})
        version = project.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()
    except Exception:
        pass

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("version") and "=" in stripped:
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return "unknown"


def _version_key(value: str) -> tuple[int, ...] | None:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)", value)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _is_remote_version_newer(current_version: str, remote_version: str) -> bool:
    if remote_version == current_version:
        return False

    current_key = _version_key(current_version)
    remote_key = _version_key(remote_version)
    if current_key is None or remote_key is None:
        return remote_version != "unknown" and remote_version != current_version

    width = max(len(current_key), len(remote_key))
    padded_current = current_key + (0,) * (width - len(current_key))
    padded_remote = remote_key + (0,) * (width - len(remote_key))
    return padded_remote > padded_current


def _parse_github_remote(remote_url: str) -> tuple[str, str] | None:
    normalized = remote_url.strip()
    for pattern in _GITHUB_REMOTE_PATTERNS:
        match = pattern.match(normalized)
        if match:
            return match.group("owner"), match.group("repo")
    return None


def _read_origin_remote_url() -> str:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        cwd=str(_PROJECT_ROOT),
        timeout=5,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _resolve_repository_location(remote_url: str | None = None) -> RepositoryLocation:
    parsed = _parse_github_remote(remote_url or "")
    if not parsed:
        return _DEFAULT_REPOSITORY

    owner, name = parsed
    return RepositoryLocation(
        owner=owner,
        name=name,
        remote_url=f"https://github.com/{owner}/{name}.git",
        api_url=f"https://api.github.com/repos/{owner}/{name}",
    )


def _redact_remote_credentials(text: str) -> str:
    return re.sub(r"://[^/\s@]+@", "://***@", text)


def _read_git_credentials(remote_url: str) -> tuple[str, str] | None:
    parsed = urlsplit(remote_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None

    query_lines = [
        f"protocol={parsed.scheme}",
        f"host={parsed.hostname}",
    ]
    if parsed.port is not None:
        query_lines.append(f"port={parsed.port}")
    path = parsed.path.lstrip("/")
    if path:
        query_lines.append(f"path={path}")

    try:
        result = subprocess.run(
            ["git", "credential", "fill"],
            input="\n".join(query_lines) + "\n\n",
            capture_output=True,
            text=True,
            cwd=str(_PROJECT_ROOT),
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            timeout=10,
            check=False,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value

    username = values.get("username", "").strip()
    password = values.get("password", "").strip()
    if not username or not password:
        return None
    return username, password


def _apply_git_credentials_to_remote_url(remote_url: str) -> str:
    parsed = urlsplit(remote_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return remote_url
    if parsed.username or parsed.password:
        return remote_url

    credentials = _read_git_credentials(remote_url)
    if credentials is None:
        return remote_url

    username, password = credentials
    host = parsed.hostname
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"

    return urlunsplit(
        (
            parsed.scheme,
            f"{quote(username, safe='')}:{quote(password, safe='')}@{host}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def _select_update_remote_url(
    config: AutoUpdateConfig,
    origin_remote_url: str | None = None,
) -> str:
    configured = config.repository_url.strip()
    if configured:
        return configured

    origin = (origin_remote_url or "").strip()
    if origin:
        return origin

    return _DEFAULT_REPOSITORY.remote_url


def _resolve_update_remote_reference(
    config: AutoUpdateConfig,
    origin_remote_url: str | None = None,
) -> str:
    return _apply_git_credentials_to_remote_url(
        _select_update_remote_url(config, origin_remote_url)
    )


def _run_git_command(args: list[str], *, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=str(_PROJECT_ROOT),
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        command_name = args[0] if args else "command"
        raise RuntimeError(f"git {command_name} timed out while contacting the update source") from exc

    if result.returncode != 0:
        error_text = result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args[:1])} failed"
        raise RuntimeError(_redact_remote_credentials(error_text))
    return result.stdout


def _parse_ls_remote_head(output: str) -> tuple[str, str]:
    default_branch = "main"
    head_sha = ""
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("ref: ") and stripped.endswith(" HEAD"):
            parts = stripped.split()
            if len(parts) >= 3:
                ref_name = parts[1]
                if ref_name.startswith("refs/heads/"):
                    default_branch = ref_name.removeprefix("refs/heads/")
        elif stripped.endswith("\tHEAD"):
            head_sha = stripped.split()[0][:8]
    return default_branch, head_sha


def _read_remote_version_info(remote_ref: str) -> dict[str, Any]:
    ls_remote_output = _run_git_command(["ls-remote", "--symref", remote_ref, "HEAD"], timeout=30)
    default_branch, remote_head_sha = _parse_ls_remote_head(ls_remote_output)

    _run_git_command(["fetch", "--depth=1", remote_ref, default_branch], timeout=60)
    remote_file_text = _run_git_command(["show", f"FETCH_HEAD:{_VERSION_RELATIVE_PATH}"], timeout=15)
    remote_version = _read_version_from_text(remote_file_text)
    if remote_version == "unknown":
        raise RuntimeError("Cannot parse remote version file")

    commit_lines = _run_git_command(
        ["show", "--no-patch", "--format=%H%n%cI%n%s", "FETCH_HEAD"],
        timeout=15,
    ).splitlines()

    commit_sha = remote_head_sha
    commit_date = ""
    commit_message = ""
    if commit_lines:
        commit_sha = commit_lines[0][:8]
    if len(commit_lines) >= 2:
        commit_date = commit_lines[1].strip()
    if len(commit_lines) >= 3:
        commit_message = commit_lines[2].strip()

    return {
        "version": remote_version,
        "default_branch": default_branch,
        "sha": commit_sha,
        "date": commit_date,
        "message": commit_message,
    }


async def _fetch_remote_version_info() -> dict[str, Any]:
    """Fetch the remote version file and latest commit metadata from the configured git remote."""
    config = await asyncio.to_thread(_read_auto_update_config)
    remote_url = await asyncio.to_thread(_read_origin_remote_url)
    remote_ref = await asyncio.to_thread(_resolve_update_remote_reference, config, remote_url)
    return await asyncio.to_thread(_read_remote_version_info, remote_ref)


def _read_auto_update_config() -> AutoUpdateConfig:
    """Read auto-update config from disk."""
    try:
        if _AUTO_UPDATE_CONFIG.exists():
            data = json.loads(_AUTO_UPDATE_CONFIG.read_text())
            return AutoUpdateConfig(**data)
    except Exception:
        pass
    return AutoUpdateConfig()


def _write_auto_update_config(cfg: AutoUpdateConfig) -> None:
    """Persist auto-update config."""
    _AUTO_UPDATE_CONFIG.write_text(json.dumps(cfg.model_dump(), indent=2))


def _get_local_head_sha() -> str:
    """Get current local HEAD short SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            capture_output=True, text=True, cwd=str(_PROJECT_ROOT), timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _ensure_origin_remote() -> None:
    """Ensure a usable origin remote exists without overwriting an existing repository source."""
    remotes = subprocess.run(
        ["git", "remote"],
        capture_output=True,
        text=True,
        cwd=str(_PROJECT_ROOT),
        timeout=10,
        check=False,
    )
    if remotes.returncode != 0:
        raise RuntimeError(remotes.stderr.strip() or "git remote failed")

    remote_names = {line.strip() for line in remotes.stdout.splitlines() if line.strip()}
    if "origin" in remote_names:
        return

    command = ["git", "remote", "add", "origin", _DEFAULT_REPOSITORY.remote_url]
    sync_result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(_PROJECT_ROOT),
        timeout=10,
        check=False,
    )
    if sync_result.returncode != 0:
        raise RuntimeError(sync_result.stderr.strip() or "failed to configure git remote")


def _frontend_install_command() -> list[str]:
    if shutil.which("pnpm"):
        return ["pnpm", "install", "--frozen-lockfile"]
    if shutil.which("corepack"):
        return ["corepack", "pnpm", "install", "--frozen-lockfile"]
    if shutil.which("npm"):
        return ["npm", "install"]
    raise RuntimeError("No supported frontend package manager found")


# ---------- endpoints ---------------------------------------------------

@router.get("/version")
async def get_version() -> dict[str, str]:
    """Return current system version and commit."""
    return {
        "version": _read_current_version(),
        "commit": _get_local_head_sha(),
    }


@router.get("/update/check")
async def check_update() -> UpdateInfo:
    """Check the configured remote repository for an updated version file."""
    current_version = _read_current_version()

    try:
        remote = await _fetch_remote_version_info()
    except Exception as exc:
        logger.warning("Failed to check for updates: %s", exc)
        raise HTTPException(status_code=502, detail=f"Cannot reach update source: {exc}") from exc

    remote_version = str(remote.get("version") or "unknown")
    has_update = _is_remote_version_newer(current_version, remote_version)

    return UpdateInfo(
        current_version=current_version,
        latest_version=remote_version,
        has_update=has_update,
        latest_commit=str(remote.get("sha") or ""),
        latest_date=remote.get("date", ""),
        changelog=remote.get("message", ""),
    )


@router.post("/update/apply")
async def apply_update() -> UpdateResult:
    """Pull the latest code from GitHub and restart the full stack.

    This preserves all user configuration (config.yaml, .env, data/) by doing
    a git pull + dependency install + full-stack restart.
    """
    try:
        remote = await _fetch_remote_version_info()
        current_version = _read_current_version()
        latest_version = str(remote.get("version") or "unknown")
        default_branch = str(remote.get("default_branch") or "main")

        if not _is_remote_version_newer(current_version, latest_version):
            return UpdateResult(success=False, message="System is already up to date.", new_version=current_version)

        auto_config = await asyncio.to_thread(_read_auto_update_config)
        origin_remote_url = await asyncio.to_thread(_read_origin_remote_url)
        update_remote_ref = await asyncio.to_thread(
            _resolve_update_remote_reference,
            auto_config,
            origin_remote_url,
        )

        # 1. fetch the target branch and fast-forward locally without relying on interactive git prompts.
        await asyncio.to_thread(
            _run_git_command,
            ["fetch", "--depth=1", update_remote_ref, default_branch],
            timeout=60,
        )

        merge = await asyncio.to_thread(
            subprocess.run,
            ["git", "merge", "--ff-only", "FETCH_HEAD"],
            capture_output=True,
            text=True,
            cwd=str(_PROJECT_ROOT),
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            timeout=60,
            check=False,
        )
        if merge.returncode != 0:
            merge = await asyncio.to_thread(
                subprocess.run,
                ["git", "rebase", "FETCH_HEAD"],
                capture_output=True,
                text=True,
                cwd=str(_PROJECT_ROOT),
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                timeout=60,
                check=False,
            )
        if merge.returncode != 0:
            merge_error = _redact_remote_credentials(merge.stderr.strip() or merge.stdout.strip())
            return UpdateResult(success=False, message=f"git update failed: {merge_error}")

        # 2. Install backend dependencies (if requirements changed)
        pip_exe = _PROJECT_ROOT / "backend" / ".venv" / "bin" / "pip"
        if pip_exe.exists():
            backend_install = await asyncio.to_thread(
                subprocess.run,
                [str(pip_exe), "install", "-e", "."],
                capture_output=True, text=True, cwd=str(_PROJECT_ROOT / "backend"), timeout=120,
            )
            if backend_install.returncode != 0:
                return UpdateResult(
                    success=False,
                    message=f"backend dependency install failed: {backend_install.stderr.strip()}",
                )

        # 3. Install frontend dependencies before the full restart rebuilds assets.
        frontend_dir = _PROJECT_ROOT / "frontend"
        if (frontend_dir / "package.json").exists():
            frontend_install = await asyncio.to_thread(
                subprocess.run,
                _frontend_install_command(),
                capture_output=True, text=True, cwd=str(frontend_dir), timeout=180,
            )
            if frontend_install.returncode != 0:
                return UpdateResult(
                    success=False,
                    message=f"frontend dependency install failed: {frontend_install.stderr.strip()}",
                )

        new_version = _read_current_version()

        # 4. Schedule a graceful full-stack restart (async — don't block the response)
        asyncio.get_running_loop().call_later(1.0, _schedule_restart)

        return UpdateResult(
            success=True,
            message=f"Update to {latest_version} downloaded. Restarting services now.",
            new_version=new_version,
        )

    except Exception as exc:
        logger.exception("Update failed")
        return UpdateResult(success=False, message=f"Update failed: {exc}")


def _schedule_restart() -> None:
    """Restart OctoAgent services after update."""
    try:
        for service_name in ("octoagent-local.service", "octoagent.service", "octoagent-gateway.service"):
            result = subprocess.run(
                ["systemctl", "restart", service_name],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if result.returncode == 0:
                logger.info("Restart scheduled via systemd service %s", service_name)
                return

        start_script = _PROJECT_ROOT / "scripts" / "start-daemon.sh"
        if start_script.exists():
            subprocess.Popen(
                ["bash", str(start_script), "--prod"],
                cwd=str(_PROJECT_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            logger.info("Restart scheduled via %s", start_script)
            return

        logger.info("Restart scheduled — please manually restart services if systemd is not configured.")
    except Exception:
        logger.exception("Failed to schedule OctoAgent restart")


# ---------- auto-update config ------------------------------------------

@router.get("/update/auto-config")
async def get_auto_update_config() -> AutoUpdateConfig:
    """Get auto-update configuration."""
    return _read_auto_update_config()


@router.post("/update/auto-config")
async def set_auto_update_config(cfg: AutoUpdateConfig) -> AutoUpdateConfig:
    """Set auto-update configuration."""
    cfg.last_check = cfg.last_check or datetime.now(UTC).isoformat()
    _write_auto_update_config(cfg)
    return cfg
