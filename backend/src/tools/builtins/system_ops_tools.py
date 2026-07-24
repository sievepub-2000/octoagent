from __future__ import annotations

import base64
import fnmatch
import hashlib
import http.client
import json
import mimetypes
import os
import posixpath
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Iterable
from datetime import UTC, datetime
from html import escape as html_escape
from pathlib import Path
from typing import Any
from uuid import uuid4

import psutil
from langchain_core.tools import tool

from src.gateway.observability import record_exception_trace, record_tool_trace
from src.harness.artifact_governance import cleanup_artifacts, policy_snapshot
from src.runtime.config.paths import get_paths
from src.runtime.governance import get_runtime_worker_isolation
from src.tools.managed_tools import list_managed_tools, register_managed_tool, uninstall_managed_tool
from src.utils.agent_tool_guide import generate_agent_tool_guide
from src.utils.datetime import utc_now_iso_seconds as _utc_now
from src.utils.serialization import fmt_json as _json

_REPO_ROOT = Path(__file__).resolve().parents[4]
_FRONTEND_ROOT = _REPO_ROOT / "frontend"
_SYSTEM_TOOL_ARTIFACT_ROOT = _REPO_ROOT / "runtime" / "system_tools"
_MAX_TEXT_BYTES = 1_000_000
_DEFAULT_CONFIG_PATTERNS = (
    "config.yaml",
    "config.example.yaml",
    "backend/pyproject.toml",
    "frontend/package.json",
    "README.md",
    "project_docs/**/*.md",
)
_SKIPPED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "cache",
    "dist",
    "logs",
    "node_modules",
    "runtime",
}
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{20,}")),
    ("openai_api_key", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_\-]{20,}")),
    ("github_token", re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("aws_access_key", re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "generic_secret_assignment",
        re.compile(r"(?i)(?:^|\s)(?:[A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API[_-]?KEY))\s*=\s*['\"]?([A-Za-z0-9_\-./+=]{12,})"),
    ),
)


def _safe_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _safe_float(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def _safe_artifact_name(value: str | None, *, prefix: str) -> str:
    raw = (value or "").strip()
    if raw.lower() in {"null", "none", "undefined"}:
        raw = ""
    if not raw:
        raw = f"{prefix}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip(".-_")
    return slug[:80] or f"{prefix}-{uuid4().hex[:8]}"


def _ensure_artifact_tool_root(tool_name: str) -> Path:
    root = (_SYSTEM_TOOL_ARTIFACT_ROOT / tool_name).resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        user = os.environ.get("USER") or str(os.geteuid())
        raise PermissionError(f"system tool artifact root is not writable by {user}: {root}; repair the Docker volume ownership") from exc
    if not os.access(root, os.W_OK | os.X_OK):
        user = os.environ.get("USER") or str(os.geteuid())
        raise PermissionError(f"system tool artifact root is not writable by {user}: {root}; repair the Docker volume ownership")
    return root


def _artifact_dir(tool_name: str, output_name: str | None) -> Path:
    artifact_name = _safe_artifact_name(output_name, prefix=tool_name)
    root = _ensure_artifact_tool_root(tool_name) / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    target = (root / artifact_name).resolve()
    if not (target == root or root in target.parents):
        raise ValueError(f"invalid artifact path: {target}")
    try:
        target.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        user = os.environ.get("USER") or str(os.geteuid())
        raise PermissionError(f"system tool artifact directory is not writable by {user}: {target}") from exc
    return target


def _tool_directory_name(value: str) -> str:
    return _safe_artifact_name(value, prefix="tool")


def _ensure_tool_python_env(tool_name: str) -> Path:
    tool_root = _ensure_artifact_tool_root(_tool_directory_name(tool_name))
    venv_dir = tool_root / ".venv"
    python_path = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if python_path.exists():
        return python_path
    # Keep the registered entrypoint physically inside the managed root.  On
    # POSIX, venv otherwise symlinks ``bin/python`` to the system interpreter,
    # which correctly fails our no-path-escape check and makes the tool
    # non-callable in Harness.
    result = subprocess.run(
        [sys.executable, "-m", "venv", "--copies", str(venv_dir)],
        cwd=str(tool_root),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"failed to create tool environment at {venv_dir}: {result.stderr[-2000:]}")
    return python_path


def _node_package_file(package_name: str, relative_path: str) -> Path:
    return (_FRONTEND_ROOT / "node_modules" / package_name / relative_path).resolve()


def _find_playwright_chromium() -> str | None:
    roots = [
        _REPO_ROOT / "runtime" / "cache" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
    ]
    for root in roots:
        if not root.exists():
            continue
        for executable in sorted(root.glob("chromium-*/chrome-linux/chrome"), reverse=True):
            if executable.exists() and os.access(executable, os.X_OK):
                return str(executable)
    return None


def _allowed_roots() -> list[Path]:
    roots = [_REPO_ROOT]
    try:
        roots.append(get_paths().base_dir.resolve())
    except Exception:
        pass
    roots.append(Path("/tmp").resolve())
    return roots


def _resolve_requested_path(path: str | None, *, default: Path = _REPO_ROOT) -> Path:
    requested = Path(path).expanduser() if path else default
    if not requested.is_absolute():
        requested = default / requested
    resolved = requested.resolve()
    allowed = _allowed_roots()
    if not any(resolved == root or root in resolved.parents for root in allowed):
        allowed_text = ", ".join(str(root) for root in allowed)
        raise ValueError(f"path is outside OctoAgent managed roots: {resolved}. allowed_roots={allowed_text}")
    return resolved


def _mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _is_skipped_path(path: Path) -> bool:
    return any(part in _SKIPPED_DIR_NAMES for part in path.parts)


def _is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in {
        ".avif",
        ".bin",
        ".bmp",
        ".gif",
        ".ico",
        ".jpg",
        ".jpeg",
        ".mp3",
        ".mp4",
        ".ogg",
        ".pdf",
        ".png",
        ".pyc",
        ".sqlite",
        ".webm",
        ".webp",
        ".zip",
    }:
        return False
    return True


def _iter_files(root: Path, *, max_files: int) -> Iterable[Path]:
    yielded = 0
    if root.is_file():
        yield root
        return
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        dir_names[:] = [name for name in dir_names if name not in _SKIPPED_DIR_NAMES]
        if _is_skipped_path(current_path.relative_to(root)):
            continue
        for file_name in file_names:
            if yielded >= max_files:
                return
            file_path = current_path / file_name
            if file_path.is_file():
                yielded += 1
                yield file_path


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_command(args: list[str], *, cwd: Path = _REPO_ROOT, timeout: int = 5) -> dict[str, Any]:
    started = time.monotonic()
    record_tool_trace("subprocess_start", tool="system_ops", args=args, cwd=str(cwd), timeout=timeout)
    try:
        with get_runtime_worker_isolation().slot("system"):
            result = subprocess.run(
                args,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
    except FileNotFoundError:
        record_tool_trace("subprocess_error", tool="system_ops", args=args, cwd=str(cwd), error="command_not_found")
        return {"available": False, "error": f"command not found: {args[0]}"}
    except subprocess.TimeoutExpired:
        record_tool_trace("subprocess_timeout", tool="system_ops", args=args, cwd=str(cwd), timeout=timeout)
        return {"available": True, "timeout": timeout}
    except Exception as exc:
        record_exception_trace("system_ops._run_command", exc, args=args, cwd=str(cwd))
        return {"available": True, "error": str(exc)}
    record_tool_trace(
        "subprocess_end",
        tool="system_ops",
        args=args,
        cwd=str(cwd),
        exit_code=result.returncode,
        duration_ms=round((time.monotonic() - started) * 1000, 3),
    )
    return {
        "available": True,
        "exit_code": result.returncode,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
    }


def _run_host_shell(command: str, *, cwd: str, timeout: int = 120) -> dict[str, Any]:
    endpoint = os.environ.get("OCTOAGENT_SYSTEM_EXECUTOR_URL", "").rstrip("/")
    token = os.environ.get("OCTOAGENT_SYSTEM_EXECUTOR_TOKEN", "")
    if not endpoint or len(token) < 32:
        return {"error": "system executor is not configured"}
    started = time.monotonic()
    record_tool_trace("shell_start", tool="host_shell", command=command, cwd=cwd, timeout=timeout)
    payload = json.dumps(
        {"command": command, "cwd": cwd, "timeout_seconds": timeout},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{endpoint}/execute",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        # The executor is an internal Compose service. Never route its bearer
        # token or request through an operator-configured outbound proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout + 35) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        record_exception_trace("system_ops._run_host_shell", exc, command=command, cwd=cwd, timeout=timeout)
        return {"error": f"system executor request failed: {type(exc).__name__}: {exc}"}
    record_tool_trace(
        "shell_end",
        tool="host_shell",
        command=command,
        cwd=cwd,
        exit_code=result.get("exit_code"),
        duration_ms=round((time.monotonic() - started) * 1000, 3),
        stdout_preview=str(result.get("stdout") or "")[-1200:],
        stderr_preview=str(result.get("stderr") or "")[-1200:],
    )
    return result


def _resolve_host_path(path: str) -> str:
    value = str(path or ".").strip()
    if value.startswith("/"):
        return posixpath.normpath(value)
    root = os.environ.get("OCTOAGENT_HOST_REPO_ROOT", "/") or "/"
    return posixpath.normpath(posixpath.join(root, value))


def _run_node_script(script_path: Path, config_path: Path, *, timeout: int) -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        return {"available": False, "error": "node executable not found"}
    started = time.monotonic()
    args = [node, str(script_path), str(config_path)]
    record_tool_trace("subprocess_start", tool="system_ops.node", args=args, cwd=str(_FRONTEND_ROOT), timeout=timeout)
    try:
        with get_runtime_worker_isolation().slot("system"):
            result = subprocess.run(args, cwd=str(_FRONTEND_ROOT), capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        record_tool_trace("subprocess_timeout", tool="system_ops.node", args=args, cwd=str(_FRONTEND_ROOT), timeout=timeout)
        return {"available": True, "timeout": timeout}
    except Exception as exc:
        record_exception_trace("system_ops._run_node_script", exc, args=args, cwd=str(_FRONTEND_ROOT), timeout=timeout)
        return {"available": True, "error": str(exc)}
    record_tool_trace(
        "subprocess_end",
        tool="system_ops.node",
        args=args,
        cwd=str(_FRONTEND_ROOT),
        exit_code=result.returncode,
        duration_ms=round((time.monotonic() - started) * 1000, 3),
    )
    return {
        "available": True,
        "exit_code": result.returncode,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
    }


def _read_version() -> str | None:
    pyproject = _REPO_ROOT / "backend" / "pyproject.toml"
    if not pyproject.exists():
        return None
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def _process_snapshot(name_filter: str, *, max_processes: int) -> list[dict[str, Any]]:
    normalized_filter = name_filter.strip().lower()
    rows: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "ppid", "name", "cmdline", "username", "status", "create_time"]):
        try:
            info = proc.info
            cmdline = " ".join(str(part) for part in (info.get("cmdline") or []))
            haystack = f"{info.get('name') or ''} {cmdline}".lower()
            if normalized_filter and normalized_filter not in haystack:
                continue
            rows.append(
                {
                    "pid": info.get("pid"),
                    "ppid": info.get("ppid"),
                    "name": info.get("name"),
                    "status": info.get("status"),
                    "username": info.get("username"),
                    "cmdline": cmdline[:300],
                    "create_time": info.get("create_time"),
                }
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    rows.sort(key=lambda item: (str(item.get("name") or ""), int(item.get("pid") or 0)))
    return rows[:max_processes]


@tool("runtime_health_report", parse_docstring=True)
def runtime_health_report_tool(
    service_name: str = "",
    process_filter: str = "octoagent",
    max_processes: int = 20,
) -> str:
    """Return a compact OctoAgent host/runtime health report.

    Args:
        service_name: Optional host systemd service name to inspect. OctoAgent
            itself is Docker-only and has no systemd unit.
        process_filter: Process name or command substring to include.
        max_processes: Maximum matching processes returned.
    """

    repo_disk = psutil.disk_usage(str(_REPO_ROOT))
    workspace_root = get_paths().base_dir
    workspace_disk = psutil.disk_usage(str(workspace_root)) if workspace_root.exists() else None
    systemd = None
    if service_name.strip() and shutil.which("systemctl"):
        active = _run_command(["systemctl", "is-active", service_name.strip()], timeout=3)
        failed = _run_command(["systemctl", "is-failed", service_name.strip()], timeout=3)
        systemd = {
            "service": service_name.strip(),
            "is_active": active.get("stdout") or active.get("error"),
            "is_failed": failed.get("stdout") or failed.get("error"),
        }

    payload = {
        "generated_at": _utc_now(),
        "repo_root": str(_REPO_ROOT),
        "version": _read_version(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory": dict(psutil.virtual_memory()._asdict()),
        "disk": {
            "repo": dict(repo_disk._asdict()),
            "workspace": dict(workspace_disk._asdict()) if workspace_disk else None,
        },
        "git": _run_command(["git", "status", "--short"], timeout=5),
        "systemd": systemd,
        "processes": _process_snapshot(process_filter, max_processes=_safe_int(max_processes, minimum=1, maximum=80)),
    }
    return _json(payload)


@tool("security_audit_scan", parse_docstring=True)
def security_audit_scan_tool(root: str = ".", max_files: int = 2500, max_findings: int = 100) -> str:
    """Scan OctoAgent-managed files for common secret and unsafe-token patterns.

    Args:
        root: File or directory under the OctoAgent repo/workspace to scan.
        max_files: Maximum files to inspect.
        max_findings: Maximum findings returned.
    """

    resolved_root = _resolve_requested_path(root)
    findings: list[dict[str, Any]] = []
    scanned = 0
    skipped_binary = 0
    for path in _iter_files(resolved_root, max_files=_safe_int(max_files, minimum=1, maximum=20_000)):
        if not _is_probably_text(path):
            skipped_binary += 1
            continue
        scanned += 1
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")[:_MAX_TEXT_BYTES]
        except OSError:
            continue
        for line_no, line in enumerate(content.splitlines(), start=1):
            for finding_type, pattern in _SECRET_PATTERNS:
                for match in pattern.finditer(line):
                    matched_text = match.group(0)
                    if finding_type == "generic_secret_assignment" and match.lastindex:
                        matched_text = match.group(1)
                    findings.append(
                        {
                            "type": finding_type,
                            "file": str(path.relative_to(_REPO_ROOT)) if path.is_relative_to(_REPO_ROOT) else str(path),
                            "line": line_no,
                            "masked_sample": _mask_secret(matched_text),
                        }
                    )
                    if len(findings) >= _safe_int(max_findings, minimum=1, maximum=500):
                        return _json(
                            {
                                "generated_at": _utc_now(),
                                "root": str(resolved_root),
                                "scanned_files": scanned,
                                "skipped_binary_files": skipped_binary,
                                "truncated": True,
                                "findings": findings,
                            }
                        )
    return _json(
        {
            "generated_at": _utc_now(),
            "root": str(resolved_root),
            "scanned_files": scanned,
            "skipped_binary_files": skipped_binary,
            "truncated": False,
            "findings": findings,
        }
    )


def _patterns_from_csv(include_globs: str | None) -> tuple[str, ...]:
    if not include_globs:
        return _DEFAULT_CONFIG_PATTERNS
    patterns = tuple(part.strip() for part in include_globs.split(",") if part.strip())
    return patterns or _DEFAULT_CONFIG_PATTERNS


def _matches_any(path: Path, patterns: tuple[str, ...]) -> bool:
    relative = path.relative_to(_REPO_ROOT).as_posix() if path.is_relative_to(_REPO_ROOT) else path.name
    return any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def _snapshot_files(root: Path, patterns: tuple[str, ...], *, max_files: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _iter_files(root, max_files=max_files):
        if not _matches_any(path, patterns):
            continue
        stat = path.stat()
        rows.append(
            {
                "path": str(path.relative_to(_REPO_ROOT)) if path.is_relative_to(_REPO_ROOT) else str(path),
                "sha256": _hash_file(path),
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(timespec="seconds"),
            }
        )
    rows.sort(key=lambda row: row["path"])
    return rows


@tool("config_drift_snapshot", parse_docstring=True)
def config_drift_snapshot_tool(root: str = ".", include_globs: str | None = None, max_files: int = 5000) -> str:
    """Create a hash snapshot for OctoAgent configuration and documentation files.

    Args:
        root: File or directory under the OctoAgent repo/workspace.
        include_globs: Comma-separated git-style glob patterns to include.
        max_files: Maximum files to enumerate before filtering.
    """

    resolved_root = _resolve_requested_path(root)
    patterns = _patterns_from_csv(include_globs)
    return _json(
        {
            "generated_at": _utc_now(),
            "root": str(resolved_root),
            "patterns": list(patterns),
            "files": _snapshot_files(resolved_root, patterns, max_files=_safe_int(max_files, minimum=1, maximum=20_000)),
        }
    )


@tool("config_drift_check", parse_docstring=True)
def config_drift_check_tool(snapshot_json: str, root: str = ".") -> str:
    """Compare the current config snapshot with a previous config_drift_snapshot payload.

    Args:
        snapshot_json: JSON string returned by config_drift_snapshot.
        root: File or directory under the OctoAgent repo/workspace to re-scan.
    """

    baseline = json.loads(snapshot_json)
    patterns = tuple(str(pattern) for pattern in baseline.get("patterns", _DEFAULT_CONFIG_PATTERNS))
    current = json.loads(config_drift_snapshot_tool.invoke({"root": root, "include_globs": ",".join(patterns)}))
    before = {item["path"]: item for item in baseline.get("files", [])}
    after = {item["path"]: item for item in current.get("files", [])}
    added = sorted(path for path in after if path not in before)
    removed = sorted(path for path in before if path not in after)
    changed = sorted(path for path in before.keys() & after.keys() if before[path].get("sha256") != after[path].get("sha256"))
    return _json(
        {
            "generated_at": _utc_now(),
            "root": current.get("root"),
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged_count": len(before.keys() & after.keys()) - len(changed),
            "drift_detected": bool(added or removed or changed),
        }
    )


@tool("media_probe", parse_docstring=True)
def media_probe_tool(path: str) -> str:
    """Inspect local image/audio/video/3D media metadata without modifying the file.

    Args:
        path: File path under the OctoAgent repo/workspace or /tmp.
    """

    resolved_path = _resolve_requested_path(path)
    if not resolved_path.is_file():
        return _json({"error": f"file not found: {resolved_path}"})

    suffix = resolved_path.suffix.lower()
    mime_type, encoding = mimetypes.guess_type(str(resolved_path))
    payload: dict[str, Any] = {
        "generated_at": _utc_now(),
        "path": str(resolved_path),
        "name": resolved_path.name,
        "size": resolved_path.stat().st_size,
        "suffix": suffix,
        "mime_type": mime_type,
        "encoding": encoding,
    }

    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".avif"}:
        try:
            from PIL import Image

            with Image.open(resolved_path) as image:
                payload["image"] = {
                    "format": image.format,
                    "width": image.width,
                    "height": image.height,
                    "mode": image.mode,
                    "frames": getattr(image, "n_frames", 1),
                }
        except Exception as exc:
            payload["image_error"] = str(exc)

    if suffix in {".mp3", ".wav", ".flac", ".ogg", ".mp4", ".mov", ".mkv", ".webm"} and shutil.which("ffprobe"):
        probe = _run_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,bit_rate:stream=codec_type,codec_name,width,height",
                "-of",
                "json",
                str(resolved_path),
            ],
            timeout=10,
        )
        if probe.get("stdout"):
            try:
                payload["ffprobe"] = json.loads(str(probe["stdout"]))
            except json.JSONDecodeError:
                payload["ffprobe"] = probe
        else:
            payload["ffprobe"] = probe

    if suffix in {".obj", ".gltf", ".glb", ".fbx", ".stl", ".ply"}:
        payload["model_3d"] = {"format_hint": suffix.lstrip(".")}
        if suffix == ".obj":
            try:
                text = resolved_path.read_text(encoding="utf-8", errors="ignore")[:_MAX_TEXT_BYTES]
                payload["model_3d"].update(
                    {
                        "vertices": sum(1 for line in text.splitlines() if line.startswith("v ")),
                        "faces": sum(1 for line in text.splitlines() if line.startswith("f ")),
                    }
                )
            except OSError as exc:
                payload["model_3d"]["error"] = str(exc)

    return _json(payload)


@tool("html_to_canvas", parse_docstring=True)
def html_to_canvas_tool(
    html: str,
    selector: str = "body",
    output_name: str | None = None,
    width: int = 1280,
    height: int = 720,
    device_width: int | None = None,
    image_format: str = "png",
    quality: float = 0.95,
    timeout_seconds: int = 30,
) -> str:
    """Render HTML into a PNG or JPG artifact using the html-to-canvas package.

    Args:
        html: HTML document or snippet to render.
        selector: CSS selector to capture from the rendered document.
        output_name: Optional artifact directory and image basename.
        width: Output image width in pixels.
        height: Output image height in pixels.
        device_width: Virtual layout width for responsive HTML.
        image_format: png, jpg, or jpeg.
        quality: JPG quality from 0.1 to 1.0.
        timeout_seconds: Browser render timeout in seconds.
    """

    html_to_canvas_lib = _node_package_file("html-to-canvas", "lib.js")
    playwright_package = _node_package_file("@playwright/test", "package.json")
    if not html_to_canvas_lib.exists():
        return _json({"error": "frontend dependency html-to-canvas is not installed", "install": "cd frontend && pnpm add html-to-canvas"})
    if not playwright_package.exists():
        return _json({"error": "frontend dependency @playwright/test is not installed", "install": "cd frontend && pnpm add -D @playwright/test"})

    normalized_format = image_format.strip().lower()
    if normalized_format == "jpeg":
        normalized_format = "jpg"
    if normalized_format not in {"png", "jpg"}:
        return _json({"error": "image_format must be png, jpg, or jpeg"})
    safe_width = _safe_int(width, minimum=32, maximum=4096)
    safe_height = _safe_int(height, minimum=32, maximum=4096)
    safe_device_width = _safe_int(device_width or safe_width, minimum=32, maximum=8192)
    safe_timeout = _safe_int(timeout_seconds, minimum=1, maximum=120)
    safe_quality = _safe_float(quality, minimum=0.1, maximum=1.0)

    artifact_root = _artifact_dir("html_to_canvas", output_name)
    image_path = artifact_root / f"{artifact_root.name}.{normalized_format}"
    source_path = artifact_root / "source.html"
    config_path = artifact_root / "render-config.json"
    script_path = artifact_root / "render-html-to-canvas.mjs"
    result_path = artifact_root / "render-result.json"
    if image_path.exists():
        image_path.unlink()
    if result_path.exists():
        result_path.unlink()
    source_path.write_text(html, encoding="utf-8")
    config_path.write_text(
        json.dumps(
            {
                "htmlPath": str(source_path),
                "outPath": str(image_path),
                "resultPath": str(result_path),
                "libPath": str(html_to_canvas_lib),
                "frontendPackageJson": str(_FRONTEND_ROOT / "package.json"),
                "selector": selector or "body",
                "width": safe_width,
                "height": safe_height,
                "deviceWidth": safe_device_width,
                "format": normalized_format,
                "quality": safe_quality,
                "timeoutMs": safe_timeout * 1000,
                "chromiumExecutable": _find_playwright_chromium(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    script_path.write_text(
        """
import fs from 'node:fs/promises';
import { createRequire } from 'node:module';

const config = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
const require = createRequire(config.frontendPackageJson);
const { chromium } = require('@playwright/test');
const launchOptions = {
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
};
if (config.chromiumExecutable) {
  launchOptions.executablePath = config.chromiumExecutable;
}

const browser = await chromium.launch(launchOptions);
try {
  const page = await browser.newPage({ viewport: { width: config.width, height: config.height } });
  const html = await fs.readFile(config.htmlPath, 'utf8');
  try {
    await page.setContent(html, { waitUntil: 'networkidle', timeout: config.timeoutMs });
  } catch {
    await page.setContent(html, { waitUntil: 'load', timeout: config.timeoutMs });
  }
  const selectedHtml = await page.$eval(config.selector, (element) => element.outerHTML);
  const librarySource = await fs.readFile(config.libPath, 'utf8');
  await page.addScriptTag({
    content: `(() => { const module = { exports: {} }; const exports = module.exports; ${librarySource}\n; window.__htmlToCanvas = module.exports; })();`,
  });
    let engine = 'html-to-canvas';
    let fallbackReason = null;
    try {
        const dataUrl = await page.evaluate(async ({ selectedHtml, options, format }) => {
            const api = window.__htmlToCanvas;
            if (!api) throw new Error('html-to-canvas package did not expose an API');
            const render = format === 'jpg' ? api.html2jpg : api.html2png;
            return await render(selectedHtml, options);
        }, {
            selectedHtml,
            format: config.format,
            options: {
                width: config.width,
                height: config.height,
                deviceWidth: config.deviceWidth,
                quality: config.quality,
            },
        });
        const encoded = dataUrl.split(',')[1];
        if (!encoded) throw new Error('html-to-canvas returned an empty data URL');
        await fs.writeFile(config.outPath, Buffer.from(encoded, 'base64'));
    } catch (error) {
        engine = 'playwright-screenshot-fallback';
        fallbackReason = error && error.message ? error.message : String(error);
        const screenshotOptions = { path: config.outPath, type: config.format === 'jpg' ? 'jpeg' : 'png' };
        if (screenshotOptions.type === 'jpeg') screenshotOptions.quality = Math.round(config.quality * 100);
        await page.locator(config.selector).first().screenshot(screenshotOptions);
    }
    await fs.writeFile(config.resultPath, JSON.stringify({ engine, fallbackReason }, null, 2));
} finally {
  await browser.close();
}
""".strip(),
        encoding="utf-8",
    )

    result = _run_node_script(script_path, config_path, timeout=safe_timeout + 15)
    if result.get("exit_code") != 0 or not image_path.exists():
        return _json({"error": "html_to_canvas render failed", "artifact_dir": str(artifact_root), **result})
    render_result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    return _json(
        {
            "generated_at": _utc_now(),
            "tool": "html_to_canvas",
            "artifact": str(image_path),
            "source_html": str(source_path),
            "selector": selector or "body",
            "width": safe_width,
            "height": safe_height,
            "device_width": safe_device_width,
            "format": normalized_format,
            "bytes": image_path.stat().st_size,
            "engine": render_result.get("engine", "unknown"),
            "fallback_reason": render_result.get("fallbackReason"),
        }
    )


def _parse_flipbook_frames(frames_json: str) -> list[Path]:
    data = json.loads(frames_json)
    if isinstance(data, dict):
        data = data.get("frames") or data.get("images") or []
    if not isinstance(data, list):
        raise ValueError("frames_json must be a JSON list or an object with frames/images")
    paths: list[Path] = []
    for index, item in enumerate(data, start=1):
        raw_path: str | None
        if isinstance(item, str):
            raw_path = item
        elif isinstance(item, dict):
            raw_path = item.get("path") or item.get("image") or item.get("file")
        else:
            raw_path = None
        if not raw_path:
            raise ValueError(f"frame {index} is missing a path")
        resolved = _resolve_requested_path(raw_path)
        if not resolved.exists() or not resolved.is_file():
            raise ValueError(f"frame {index} does not exist: {resolved}")
        paths.append(resolved)
    if not paths:
        raise ValueError("frames_json must include at least one frame")
    return paths


@tool("flipbook", parse_docstring=True)
def flipbook_tool(
    frames_json: str,
    output_name: str | None = None,
    title: str = "OctoAgent Flipbook",
    width: int = 960,
    speed: float = 0.5,
    autoplay: bool = False,
) -> str:
    """Create a browser flipbook artifact from image frames using the flipbook package.

    Args:
        frames_json: JSON list of image paths, or an object with frames/images.
        output_name: Optional artifact directory basename.
        title: HTML document title.
        width: Maximum flipbook viewport width in pixels.
        speed: Scroll speed from 0.0 to 1.0.
        autoplay: Whether to loop frames like a GIF without scrolling.
    """

    flipbook_lib = _node_package_file("flipbook", "flipbook.js")
    if not flipbook_lib.exists():
        return _json({"error": "frontend dependency flipbook is not installed", "install": "cd frontend && pnpm add flipbook"})
    try:
        frame_paths = _parse_flipbook_frames(frames_json)
    except Exception as exc:
        return _json({"error": str(exc)})

    extensions = {("jpg" if path.suffix.lower() == ".jpeg" else path.suffix.lower().lstrip(".")) for path in frame_paths}
    allowed_extensions = {"png", "jpg", "webp", "gif"}
    if not extensions <= allowed_extensions:
        return _json({"error": "frames must be png, jpg, jpeg, webp, or gif", "extensions": sorted(extensions)})
    if len(extensions) != 1:
        return _json({"error": "flipbook frames must share one image extension", "extensions": sorted(extensions)})

    extension = next(iter(extensions))
    artifact_root = _artifact_dir("flipbook", output_name)
    frames_dir = artifact_root / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old_frame in frames_dir.iterdir():
        if old_frame.is_file():
            old_frame.unlink()
    for index, source in enumerate(frame_paths, start=1):
        shutil.copy2(source, frames_dir / f"frame-{index:04d}.{extension}")
    shutil.copy2(flipbook_lib, artifact_root / "flipbook.js")

    safe_width = _safe_int(width, minimum=160, maximum=4096)
    safe_speed = _safe_float(speed, minimum=0.0, maximum=1.0)
    escaped_title = html_escape(title or "OctoAgent Flipbook")
    index_path = artifact_root / "index.html"
    index_path.write_text(
        f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{escaped_title}</title>
  <style>
    html, body {{ margin: 0; min-height: 100%; background: #111; color: #f8fafc; font-family: ui-sans-serif, system-ui, sans-serif; }}
    main {{ width: min(100vw, {safe_width}px); margin: 0 auto; }}
    header {{ padding: 16px; }}
    h1 {{ margin: 0; font-size: 18px; font-weight: 650; }}
    #octo-flipbook {{ width: 100%; min-height: 60vh; }}
  </style>
</head>
<body>
  <main>
    <header><h1>{escaped_title}</h1></header>
    <div id=\"octo-flipbook\"></div>
  </main>
  <script src=\"./flipbook.js\"></script>
  <script>
    flipbook({{
      id: 'octo-flipbook',
      path: 'frames',
      filename: 'frame-%4d',
      extension: {json.dumps(extension)},
      count: {len(frame_paths)},
      speed: {safe_speed},
      cover: false,
      gif: {json.dumps(bool(autoplay))}
    }});
  </script>
</body>
</html>
""",
        encoding="utf-8",
    )

    return _json(
        {
            "generated_at": _utc_now(),
            "tool": "flipbook",
            "artifact": str(index_path),
            "frames_dir": str(frames_dir),
            "frame_count": len(frame_paths),
            "extension": extension,
            "width": safe_width,
            "speed": safe_speed,
            "autoplay": bool(autoplay),
        }
    )


@tool("host_shell", parse_docstring=True)
def host_shell_tool(
    command: str,
    description: str = "",
    cwd: str = ".",
    timeout_seconds: int = 120,
) -> str:
    """Run an unrestricted shell command on the OctoAgent host.

    This is the system-level escape hatch for sudo/systemctl/service/apt/pip,
    process inspection, internal-network tools, and other operator work.

    Args:
        command: Shell command to run.
        description: One-line human-readable intent shown in the chat UI
            (e.g. "鏌ョ湅 nginx 鐘舵€?). Always provide it; it is the only thing
            an operator sees before the command output streams in.
        cwd: Working directory. Relative paths resolve under the OctoAgent repo.
        timeout_seconds: Command timeout in seconds.
    """
    _ = description  # surfaced via tool-call args in the chat UI

    requested_cwd = str(cwd or ".").strip()
    target_cwd = _resolve_host_path(requested_cwd)
    safe_timeout = _safe_int(timeout_seconds, minimum=1, maximum=3600)
    result = _run_host_shell(command, cwd=target_cwd, timeout=safe_timeout)
    return _json({"generated_at": _utc_now(), "command": command, "cwd": target_cwd, **result})


@tool("host_file_manage", parse_docstring=True)
def host_file_manage_tool(
    operation: str,
    path: str,
    target_path: str | None = None,
    content: str | None = None,
    recursive: bool = False,
    parents: bool = True,
) -> str:
    """Manage files on the OctoAgent host, including external system paths.

    Args:
        operation: One of mkdir, delete, move, rename, copy, read, write, append.
        path: Source path.
        target_path: Destination path for move, rename, or copy.
        content: Text content for write or append.
        recursive: Whether delete/copy should recurse for directories.
        parents: Whether mkdir/write should create parent directories.
    """

    op = operation.strip().lower()
    source = _resolve_host_path(path)
    target = _resolve_host_path(target_path) if target_path else None
    quoted_source = shlex.quote(source)
    prefix = ""
    if parents and op in {"write", "append"}:
        prefix = f"mkdir -p -- {shlex.quote(posixpath.dirname(source) or '/')} && "
    elif parents and op in {"move", "rename", "copy"} and target:
        prefix = f"mkdir -p -- {shlex.quote(posixpath.dirname(target) or '/')} && "

    if op == "mkdir":
        command = f"mkdir {'-p ' if parents else ''}-- {quoted_source}"
    elif op == "delete":
        command = f"rm {'-rf ' if recursive else ''}-- {quoted_source}"
    elif op in {"move", "rename"}:
        if target is None:
            return _json({"error": "target_path is required"})
        command = f"{prefix}mv -- {quoted_source} {shlex.quote(target)}"
    elif op == "copy":
        if target is None:
            return _json({"error": "target_path is required"})
        command = f"{prefix}cp {'-a ' if recursive else ''}-- {quoted_source} {shlex.quote(target)}"
    elif op == "read":
        command = f"cat -- {quoted_source}"
    elif op in {"write", "append"}:
        if content is None:
            return _json({"error": "content is required"})
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        redirect = ">>" if op == "append" else ">"
        command = f"{prefix}printf %s {shlex.quote(encoded)} | base64 -d {redirect} {quoted_source}"
    else:
        return _json({"error": f"unsupported operation: {operation}"})

    result = _run_host_shell(command, cwd="/", timeout=120)
    response: dict[str, Any] = {
        "generated_at": _utc_now(),
        "operation": op,
        "path": source,
        "target_path": target,
        **result,
    }
    if op == "read" and result.get("exit_code") == 0:
        response["content"] = result.get("stdout", "")
    response["ok"] = result.get("exit_code") == 0 and not result.get("error")
    return _json(response)


@tool("tcp_connect", parse_docstring=True)
def tcp_connect_tool(host: str, port: int, send_data: str | None = None, timeout_seconds: float = 5.0) -> str:
    """Open a raw TCP connection, including localhost and private networks.

    Args:
        host: Target hostname or IP address.
        port: Target TCP port.
        send_data: Optional UTF-8 text to send after connecting.
        timeout_seconds: Socket timeout in seconds.
    """

    timeout = max(0.1, min(float(timeout_seconds), 60.0))
    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as sock:
            sock.settimeout(timeout)
            if send_data:
                sock.sendall(send_data.encode("utf-8"))
                try:
                    response = sock.recv(4096).decode("utf-8", errors="replace")
                except TimeoutError:
                    response = ""
            else:
                response = ""
        return _json({"generated_at": _utc_now(), "host": host, "port": port, "connected": True, "response": response})
    except Exception as exc:
        return _json({"generated_at": _utc_now(), "host": host, "port": port, "connected": False, "error": str(exc)})


@tool("http_transfer", parse_docstring=True)
def http_transfer_tool(
    method: str,
    url: str,
    local_path: str | None = None,
    body: str | None = None,
    headers_json: str | None = None,
    timeout_seconds: int = 60,
) -> str:
    """Upload to or download from HTTP/HTTPS endpoints, including internal hosts.

    Args:
        method: HTTP method such as GET, POST, PUT, PATCH, or DELETE.
        url: Target URL.
        local_path: Destination for GET downloads or source file for uploads.
        body: Optional request body; ignored when local_path is an upload source.
        headers_json: Optional JSON object of request headers.
        timeout_seconds: Request timeout in seconds.
    """

    headers = json.loads(headers_json) if headers_json else {}
    if not isinstance(headers, dict):
        return _json({"error": "headers_json must decode to an object"})
    normalized_method = method.strip().upper()
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return _json({"error": "url must be an absolute http(s) URL"})
    data: bytes | None = body.encode("utf-8") if body is not None else None
    path = Path(local_path).expanduser().resolve() if local_path else None
    if normalized_method in {"POST", "PUT", "PATCH"} and path and path.exists() and path.is_file():
        data = path.read_bytes()
    headers_map = {str(k): str(v) for k, v in headers.items()}
    target_path = urllib.parse.urlunparse(("", "", parsed_url.path or "/", parsed_url.params, parsed_url.query, ""))
    timeout = _safe_int(timeout_seconds, minimum=1, maximum=600)
    try:
        hostname = parsed_url.hostname
        if not hostname:
            return _json({"error": "url must include a hostname"})
        connection_cls = http.client.HTTPSConnection if parsed_url.scheme == "https" else http.client.HTTPConnection
        connection = connection_cls(hostname, parsed_url.port, timeout=timeout)
        try:
            connection.request(normalized_method, target_path, body=data, headers=headers_map)
            response = connection.getresponse()
            response_body = response.read()
        finally:
            connection.close()
        content_preview = response_body[:8000].decode("utf-8", errors="replace")
        result = {
            "generated_at": _utc_now(),
            "status": response.status,
            "headers": dict(response.getheaders()),
            "saved_to": None,
            "content_preview": content_preview,
        }
        if response.status >= 400:
            result["error"] = response.reason
            return _json(result)
        if normalized_method == "GET" and path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response_body)
            result["saved_to"] = str(path)
            result["content_preview"] = ""
        return _json(result)
    except Exception as exc:
        return _json({"error": str(exc)})


@tool("python_package_install", parse_docstring=True)
def python_package_install_tool(
    packages: str,
    target_tool: str = "python_package_install",
    python_executable: str = "",
    extra_args: str = "",
    confirmed_by_user: bool = False,
    verification_command: str = "",
) -> str:
    """Install Python packages with pip after explicit user confirmation.

    Args:
        packages: Space-separated package specifiers.
        target_tool: Tool name that owns the install. Defaults to python_package_install.
        python_executable: Optional Python executable. It must be inside runtime/system_tools/<target_tool>; otherwise installation is rejected.
        extra_args: Extra pip install arguments.
        confirmed_by_user: True only after the user explicitly approves the install target and package list.
        verification_command: Optional command to run after a successful install to verify the tool works.
    """

    if not confirmed_by_user:
        return _json(
            {
                "error": "user_confirmation_required",
                "message": "Ask the user to confirm before installing packages or tools. Confirm package list, target tool directory, and whether this changes the host OS or the OctoAgent runtime.",
                "requested_packages": packages,
                "target_tool": target_tool,
                "default_install_root": str(_SYSTEM_TOOL_ARTIFACT_ROOT / _tool_directory_name(target_tool)),
            }
        )

    if not packages.strip():
        return _json({"error": "packages is required"})
    if not verification_command.strip():
        return _json({"error": "verification_command_required"})

    clean_tool_name = _tool_directory_name(target_tool)
    tool_root = _ensure_artifact_tool_root(clean_tool_name)
    if python_executable.strip():
        py = Path(python_executable).expanduser()
        if not py.is_absolute():
            py = (_REPO_ROOT / py).resolve()
        else:
            py = py.resolve()
        if not (py == tool_root or tool_root in py.parents):
            return _json(
                {
                    "error": "python_environment_outside_managed_tool_root",
                    "message": "Install tools only under runtime/system_tools/<target_tool>.",
                    "install_root": str(tool_root),
                }
            )
        install_scope = "explicit_python_environment"
    else:
        py = _ensure_tool_python_env(clean_tool_name)
        install_scope = "tool_directory"

    args = [str(py), "-m", "pip", "install", *shlex.split(packages), *shlex.split(extra_args)]
    started = time.monotonic()
    record_tool_trace("subprocess_start", tool="python_package_install", args=args, cwd=str(tool_root), timeout=3600)
    try:
        with get_runtime_worker_isolation().slot("system"):
            result = subprocess.run(args, cwd=str(tool_root), capture_output=True, text=True, encoding="utf-8", timeout=3600, check=False)
    except Exception as exc:
        record_exception_trace("system_ops.python_package_install", exc, args=args, cwd=str(tool_root), timeout=3600)
        return _json({"error": str(exc), "args": args, "install_root": str(tool_root)})

    verification: dict[str, Any] | None = None
    if result.returncode == 0 and verification_command.strip():
        verify_args = shlex.split(verification_command)
        verify_started = time.monotonic()
        record_tool_trace("subprocess_start", tool="python_package_install.verify", args=verify_args, cwd=str(tool_root), timeout=600)
        try:
            with get_runtime_worker_isolation().slot("system"):
                verify_result = subprocess.run(verify_args, cwd=str(tool_root), capture_output=True, text=True, encoding="utf-8", timeout=600, check=False)
            verification = {
                "args": verify_args,
                "exit_code": verify_result.returncode,
                "stdout": verify_result.stdout[-4000:],
                "stderr": verify_result.stderr[-4000:],
                "duration_ms": round((time.monotonic() - verify_started) * 1000, 3),
            }
        except Exception as exc:
            record_exception_trace("system_ops.python_package_install.verify", exc, args=verify_args, cwd=str(tool_root), timeout=600)
            verification = {"args": verify_args, "error": str(exc)}

    record_tool_trace(
        "subprocess_end",
        tool="python_package_install",
        args=args,
        cwd=str(tool_root),
        exit_code=result.returncode,
        duration_ms=round((time.monotonic() - started) * 1000, 3),
    )
    manifest = None
    if result.returncode == 0 and not (verification and (verification.get("exit_code", 0) != 0 or verification.get("error"))):
        relative_python = str(py.relative_to(tool_root))
        manifest = register_managed_tool(
            clean_tool_name,
            root=_SYSTEM_TOOL_ARTIFACT_ROOT,
            source_type="python",
            source=packages,
            entrypoint=relative_python,
            invocation=f"{relative_python} -m <package_module>",
            description=f"Managed Python tool: {packages}",
            verification=verification,
        )
        generate_agent_tool_guide()
    return _json(
        {
            "generated_at": _utc_now(),
            "args": args,
            "target_tool": clean_tool_name,
            "install_root": str(tool_root),
            "install_scope": install_scope,
            "exit_code": result.returncode,
            "stdout": result.stdout[-8000:],
            "stderr": result.stderr[-8000:],
            "verification": verification,
            "manifest": manifest,
            "harness": "Updated automatically after successful installation.",
        }
    )


@tool("github_tool_install", parse_docstring=True)
def github_tool_install_tool(
    name: str,
    repository_url: str,
    ref: str,
    entrypoint: str,
    install_command: str = "",
    verification_command: str = "",
    description: str = "",
    confirmed_by_user: bool = False,
) -> str:
    """Install a pinned GitHub tool under runtime/system_tools after explicit approval.

    Args:
        name: Stable managed tool name.
        repository_url: HTTPS GitHub repository URL.
        ref: Required tag or branch selected during research.
        entrypoint: Relative executable path inside the cloned repository.
        install_command: Optional argv-style setup command executed without a shell.
        verification_command: Required argv-style smoke command executed without a shell.
        description: Harness usage description.
        confirmed_by_user: True only after the user approves source, ref, directory, and commands.
    """

    if not confirmed_by_user:
        return _json({"error": "user_confirmation_required", "name": name, "repository_url": repository_url, "ref": ref})
    parsed = urllib.parse.urlparse(repository_url.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        return _json({"error": "github_https_repository_required"})
    if not ref.strip() or not verification_command.strip():
        return _json({"error": "ref_and_verification_command_required"})
    clean_name = _tool_directory_name(name)
    root = _ensure_artifact_tool_root(clean_name)
    if any(root.iterdir()):
        return _json({"error": "managed_tool_directory_not_empty", "install_root": str(root)})
    source = root / "source"
    clone = subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", ref.strip(), repository_url.strip(), str(source)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=900,
        check=False,
    )
    if clone.returncode != 0:
        shutil.rmtree(root, ignore_errors=True)
        return _json({"error": "git_clone_failed", "exit_code": clone.returncode, "stderr": clone.stderr[-4000:]})
    install_result = None
    if install_command.strip():
        install_result = subprocess.run(shlex.split(install_command), cwd=source, capture_output=True, text=True, encoding="utf-8", timeout=1800, check=False)
        if install_result.returncode != 0:
            shutil.rmtree(root, ignore_errors=True)
            return _json({"error": "install_command_failed", "exit_code": install_result.returncode, "stderr": install_result.stderr[-4000:]})
    entry = (source / entrypoint).resolve()
    if source.resolve() not in entry.parents or not entry.exists():
        shutil.rmtree(root, ignore_errors=True)
        return _json({"error": "entrypoint_not_found_or_unsafe", "entrypoint": entrypoint})
    verify = subprocess.run(shlex.split(verification_command), cwd=source, capture_output=True, text=True, encoding="utf-8", timeout=600, check=False)
    if verify.returncode != 0:
        shutil.rmtree(root, ignore_errors=True)
        return _json({"error": "verification_failed", "exit_code": verify.returncode, "stderr": verify.stderr[-4000:]})
    manifest = register_managed_tool(
        clean_name,
        root=_SYSTEM_TOOL_ARTIFACT_ROOT,
        source_type="github",
        source=repository_url,
        version=ref,
        entrypoint=str(entry.relative_to(root)),
        invocation=str(entry.relative_to(root)),
        description=description,
        verification={"command": verification_command, "exit_code": 0, "stdout": verify.stdout[-2000:]},
    )
    generate_agent_tool_guide()
    return _json({"ok": True, "manifest": manifest, "harness": "Updated automatically."})


@tool("managed_tool_list", parse_docstring=True)
def managed_tool_list_tool() -> str:
    """List operator-installed tools from the same manifest source used by Harness."""

    return _json({"tools": list_managed_tools(root=_SYSTEM_TOOL_ARTIFACT_ROOT)})


@tool("managed_tool_execute", parse_docstring=True)
def managed_tool_execute_tool(name: str, arguments: str = "", timeout_seconds: int = 600) -> str:
    """Execute the registered entrypoint of one callable managed tool.

    Args:
        name: Managed tool name shown in Harness.
        arguments: Optional argv-style arguments passed without a shell.
        timeout_seconds: Bounded execution timeout from 1 to 1800 seconds.
    """

    manifest = next((item for item in list_managed_tools(root=_SYSTEM_TOOL_ARTIFACT_ROOT) if item.get("name") == name), None)
    if manifest is None:
        return _json({"error": "managed_tool_not_found", "name": name})
    if not manifest.get("callable"):
        return _json({"error": "managed_tool_not_callable", "name": name})
    root = Path(str(manifest["install_root"])).resolve()
    entrypoint = (root / str(manifest["entrypoint"])).resolve()
    if root not in entrypoint.parents or not entrypoint.is_file():
        return _json({"error": "managed_entrypoint_not_found_or_unsafe", "name": name})
    command = ([sys.executable, str(entrypoint)] if entrypoint.suffix.lower() == ".py" else [str(entrypoint)]) + shlex.split(arguments)
    timeout = min(1800, max(1, int(timeout_seconds)))
    started = time.monotonic()
    record_tool_trace("subprocess_start", tool=f"managed:{name}", args=command, cwd=str(entrypoint.parent), timeout=timeout)
    try:
        with get_runtime_worker_isolation().slot("system"):
            result = subprocess.run(command, cwd=entrypoint.parent, capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False)
    except Exception as exc:
        record_exception_trace(f"managed_tool.{name}", exc, args=command, cwd=str(entrypoint.parent), timeout=timeout)
        return _json({"error": str(exc), "name": name})
    record_tool_trace(
        "subprocess_end",
        tool=f"managed:{name}",
        args=command,
        cwd=str(entrypoint.parent),
        exit_code=result.returncode,
        duration_ms=round((time.monotonic() - started) * 1000, 3),
    )
    return _json({"name": name, "exit_code": result.returncode, "stdout": result.stdout[-8000:], "stderr": result.stderr[-8000:]})


@tool("managed_tool_uninstall", parse_docstring=True)
def managed_tool_uninstall_tool(name: str, confirmed_by_user: bool = False) -> str:
    """Uninstall one manifest-owned tool and remove its artifacts/cache/logs.

    Args:
        name: Managed tool name shown in Harness.
        confirmed_by_user: True only after the user approves deletion of the exact managed root.
    """

    if not confirmed_by_user:
        return _json({"error": "user_confirmation_required", "name": name})
    result = uninstall_managed_tool(name, root=_SYSTEM_TOOL_ARTIFACT_ROOT)
    if result.get("ok"):
        generate_agent_tool_guide()
    return _json({**result, "harness": "Updated automatically." if result.get("ok") else "unchanged"})


@tool("artifact_governance_status", parse_docstring=True)
def artifact_governance_status_tool() -> str:
    """Show artifact ownership, protected paths, and the current retention policy."""

    return _json(policy_snapshot())


@tool("artifact_cleanup", parse_docstring=True)
def artifact_cleanup_tool(dry_run: bool = True, confirmed_by_user: bool = False) -> str:
    """Preview or apply cleanup only inside policy-owned disposable artifact roots.

    Args:
        dry_run: True reports candidates without deletion; False applies cleanup.
        confirmed_by_user: Required when dry_run is False.
    """

    if not dry_run and not confirmed_by_user:
        return _json({"error": "user_confirmation_required", "dry_run": False})
    return _json(cleanup_artifacts(dry_run=dry_run))


@tool("process_manage", parse_docstring=True)
def process_manage_tool(operation: str = "list", pid: int | None = None, name_filter: str = "", signal_name: str = "TERM") -> str:
    """List or signal host processes.

    Args:
        operation: list or kill.
        pid: Process ID for kill.
        name_filter: Optional substring filter for list.
        signal_name: Signal name for kill, such as TERM, KILL, HUP, or INT.
    """

    op = operation.strip().lower()
    if op == "list":
        return _json({"generated_at": _utc_now(), "processes": _process_snapshot(name_filter, max_processes=200)})
    if op == "kill":
        if pid is None:
            return _json({"error": "pid is required"})
        sig = getattr(signal, f"SIG{signal_name.strip().upper()}", signal.SIGTERM)
        try:
            os.kill(int(pid), sig)
        except Exception as exc:
            return _json({"operation": op, "pid": pid, "signal": sig.name, "error": str(exc)})
        return _json({"generated_at": _utc_now(), "operation": op, "pid": pid, "signal": sig.name, "ok": True})
    return _json({"error": f"unsupported operation: {operation}"})


SYSTEM_OPS_TOOLS = [
    runtime_health_report_tool,
    security_audit_scan_tool,
    config_drift_snapshot_tool,
    config_drift_check_tool,
    media_probe_tool,
    html_to_canvas_tool,
    flipbook_tool,
    host_shell_tool,
    host_file_manage_tool,
    tcp_connect_tool,
    http_transfer_tool,
    python_package_install_tool,
    github_tool_install_tool,
    managed_tool_list_tool,
    managed_tool_execute_tool,
    managed_tool_uninstall_tool,
    artifact_governance_status_tool,
    artifact_cleanup_tool,
    process_manage_tool,
]
