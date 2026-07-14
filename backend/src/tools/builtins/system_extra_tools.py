from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from src.utils.serialization import fmt_json as _json

_REPO_ROOT = Path(__file__).resolve().parents[4]
_FRONTEND_ROOT = _REPO_ROOT / "frontend"
_ARTIFACT_ROOT = _REPO_ROOT / "runtime" / "system_tools"
_DEFAULT_DB_DSN = os.environ.get("OCTOAGENT_POSTGRES_SUPERUSER_DSN") or "postgresql:///octoagent?user=postgres"
_BACKEND_VENV_BIN = _REPO_ROOT / "backend" / ".venv" / "bin"
_MANAGED_TOOLS_DIR = _REPO_ROOT / "runtime" / "tools"
_MANAGED_BIN = _MANAGED_TOOLS_DIR / "bin"
_NODE_TOOLS_BIN = _MANAGED_TOOLS_DIR / "node_modules" / ".bin"
_SYSTEM_COMMAND_ALLOWLIST = {
    "bash",
    "curl",
    "docker",
    "git",
    "nginx",
    "node",
    "npm",
    "npx",
    "pnpm",
    "psql",
    "scp",
    "ssh",
    "sqlite3",
    "systemctl",
    "tar",
    "xz",
}


def _which(name: str) -> str | None:
    """Resolve commands using OctoAgent-managed locations first.

    Python tools must live in backend/.venv. Standalone third-party binaries live
    in runtime/tools/bin. Only OS-provided infrastructure commands fall back to
    PATH through an explicit allowlist.
    """
    for bin_dir in (_MANAGED_BIN, _BACKEND_VENV_BIN, _NODE_TOOLS_BIN):
        candidate = bin_dir / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    if name in _SYSTEM_COMMAND_ALLOWLIST:
        return shutil.which(name)
    return None


def _cmd(name: str) -> list[str]:
    exe = _which(name)
    return [exe] if exe else [name]


def _backend_python() -> str:
    python = _BACKEND_VENV_BIN / "python"
    return str(python) if python.exists() else "python3"


os.environ.setdefault("TRIVY_CACHE_DIR", str(_MANAGED_TOOLS_DIR / "trivy-cache"))

_MCP_NODE_BIN = _MANAGED_TOOLS_DIR / "mcp" / "node_modules" / ".bin"
_MCP_COMMAND_DEFAULTS = {
    "OCTOAGENT_PYTHON_BIN": str(_BACKEND_VENV_BIN / "python"),
    "OCTOAGENT_MCP_FILESYSTEM_BIN": str(_MCP_NODE_BIN / "mcp-server-filesystem"),
    "OCTOAGENT_MCP_POSTGRES_BIN": str(_MCP_NODE_BIN / "mcp-server-postgres"),
    "OCTOAGENT_MCP_OPENAPI_BIN": str(_MCP_NODE_BIN / "openapi-mcp-server"),
    "OCTOAGENT_MCP_REDIS_BIN": str(_MCP_NODE_BIN / "mcp-server-redis"),
    "OCTOAGENT_MCP_KUBERNETES_BIN": str(_MCP_NODE_BIN / "mcp-server-kubernetes"),
    "OCTOAGENT_MCP_DOCKER_BIN": str(_MCP_NODE_BIN / "docker-mcp"),
}


def _resolve_mcp_command(raw: str) -> str:
    """Resolve an MCP command field, expanding a leading $ENV placeholder.

    Mirrors scripts/start-daemon.sh defaults so the doctor reports accurately
    even when the MCP bin env vars are not exported in the current process.
    """
    raw = (raw or "").strip()
    if not raw.startswith("$"):
        return raw
    name = raw[1:]
    return os.environ.get(name) or _MCP_COMMAND_DEFAULTS.get(name, "")


def _mcp_command_missing(cfg: dict) -> bool:
    resolved = _resolve_mcp_command(str(cfg.get("command") or ""))
    if not resolved:
        return True
    if os.path.isabs(resolved):
        return not (os.path.exists(resolved) and os.access(resolved, os.X_OK))
    return not bool(shutil.which(resolved))


os.environ.setdefault("NPM_CONFIG_CACHE", str(_MANAGED_TOOLS_DIR / "npm-cache"))
os.environ.setdefault("npm_config_cache", os.environ["NPM_CONFIG_CACHE"])

_DANGEROUS_SQL = re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|call|execute|merge|vacuum|reindex)\b", re.I)
_SECRET_PATTERNS = (
    ("openai_api_key", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_\-]{20,}")),
    ("github_token", re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{20,}")),
    ("aws_access_key", re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("secret_assignment", re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{12,})")),
)


def _redact_text(value: str) -> str:
    value = value or ""
    value = re.sub(r"(postgres(?:ql)?://[^:/@\s]+:)([^@\s]+)(@)", r"\1***\3", value)
    value = re.sub(r"(?i)((?:password|passwd|token|secret|api[_-]?key)=)([^\s;&]+)", r"\1***", value)
    return value


def _safe_args(args: list[str]) -> list[str]:
    return [_redact_text(str(arg)) for arg in args]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _slug(value: str, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or fallback).strip()).strip(".-_")
    return (text or fallback)[:80]


def _artifact_dir(tool_name: str) -> Path:
    root = _ARTIFACT_ROOT / _slug(tool_name, "tool")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_artifact(tool_name: str, name: str, content: str) -> str:
    root = _artifact_dir(tool_name)
    path = root / f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{_slug(name, 'artifact')}.log"
    path.write_text(content, encoding="utf-8", errors="replace")
    return str(path)


def _clip(text: str, limit: int = 4000) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit // 2] + "\n...<truncated>...\n" + text[-limit // 2 :]


def _run(args: list[str], *, cwd: Path | None = None, timeout: int = 120, tool_name: str = "system_extra", artifact: bool = True) -> dict[str, Any]:
    started = time.monotonic()
    cwd = cwd or _REPO_ROOT
    try:
        result = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False)
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        artifact_path = None
        if artifact and (len(stdout) + len(stderr) > 4000 or result.returncode != 0):
            artifact_path = _write_artifact(tool_name, _slug(args[0], "command"), f"$ {shlex.join(_safe_args(args))}\n# cwd: {cwd}\n# exit: {result.returncode}\n\nSTDOUT\n{_redact_text(stdout)}\n\nSTDERR\n{_redact_text(stderr)}\n")
        return {
            "available": True,
            "args": _safe_args(args),
            "cwd": str(cwd),
            "exit_code": result.returncode,
            "stdout": _clip(_redact_text(stdout)),
            "stderr": _clip(_redact_text(stderr)),
            "artifact": artifact_path,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        }
    except FileNotFoundError:
        return {"available": False, "error": f"command not found: {args[0]}", "args": args}
    except subprocess.TimeoutExpired as exc:
        artifact_path = _write_artifact(tool_name, "timeout", f"$ {shlex.join(_safe_args(args))}\n# cwd: {cwd}\n# timeout: {timeout}\n\nSTDOUT\n{_redact_text(exc.stdout or '')}\n\nSTDERR\n{_redact_text(exc.stderr or '')}\n")
        return {"available": True, "timeout": timeout, "args": _safe_args(args), "cwd": str(cwd), "artifact": artifact_path}
    except Exception as exc:
        return {"available": True, "error": str(exc), "args": _safe_args(args), "cwd": str(cwd)}


def _resolve_path(path: str | None, *, default: Path = _REPO_ROOT, must_exist: bool = False) -> Path:
    p = Path(path).expanduser() if path else default
    if not p.is_absolute():
        p = default / p
    p = p.resolve()
    if must_exist and not p.exists():
        raise ValueError(f"path does not exist: {p}")
    return p


def _require_confirmation(confirmed_by_user: bool, action: str) -> str | None:
    if confirmed_by_user:
        return None
    return _json({"error": "user_confirmation_required", "action": action, "message": "This system-level operation requires the chat permission/approval mode to authorize it."})


def _safe_db_query(sql: str) -> str | None:
    stripped = sql.strip().rstrip(";")
    if not stripped:
        return "sql is required"
    if ";" in stripped:
        return "multiple SQL statements are not allowed"
    if _DANGEROUS_SQL.search(stripped):
        return "write or administrative SQL is not allowed by this read-only tool"
    if not re.match(r"^(select|with|explain|show)\b", stripped, re.I):
        return "only SELECT/WITH/EXPLAIN/SHOW statements are allowed"
    return None


@tool("docker_status", parse_docstring=True)
def docker_status_tool() -> str:
    """Check Docker client and daemon availability."""
    return _json(
        {
            "generated_at": _now(),
            "version": _run(
                _cmd("docker") + ["version", "--format", "{{json .}}"],
                timeout=10,
                tool_name="docker_status",
            ),
            "info": _run(
                _cmd("docker") + ["info", "--format", "{{json .}}"],
                timeout=10,
                tool_name="docker_status",
            ),
        }
    )


@tool("docker_ps", parse_docstring=True)
def docker_ps_tool(all_containers: bool = False) -> str:
    """List Docker containers.

    Args:
        all_containers: Include stopped containers.
    """
    args = _cmd("docker") + ["ps", "--format", "json"]
    if all_containers:
        args.insert(2, "--all")
    return _json({"generated_at": _now(), "result": _run(args, timeout=20, tool_name="docker_ps")})


@tool("docker_images", parse_docstring=True)
def docker_images_tool() -> str:
    """List Docker images."""
    return _json({"generated_at": _now(), "result": _run(_cmd("docker") + ["images", "--format", "json"], timeout=20, tool_name="docker_images")})


@tool("docker_logs", parse_docstring=True)
def docker_logs_tool(container: str, tail: int = 200) -> str:
    """Read Docker container logs.

    Args:
        container: Container name or ID.
        tail: Number of log lines.
    """
    return _json({"generated_at": _now(), "container": container, "result": _run(_cmd("docker") + ["logs", "--tail", str(max(1, min(int(tail), 2000))), container], timeout=30, tool_name="docker_logs")})


@tool("docker_inspect", parse_docstring=True)
def docker_inspect_tool(target: str) -> str:
    """Inspect a Docker object.

    Args:
        target: Container, image, volume, or network name/ID.
    """
    return _json({"generated_at": _now(), "target": target, "result": _run(_cmd("docker") + ["inspect", target], timeout=30, tool_name="docker_inspect")})


@tool("docker_compose_plan", parse_docstring=True)
def docker_compose_plan_tool(compose_file: str = "docker/docker-compose-dev.yaml", project_name: str = "octoagent-dev") -> str:
    """Validate/render a Docker Compose plan without applying it.

    Args:
        compose_file: Compose file path.
        project_name: Compose project name.
    """
    path = _resolve_path(compose_file, must_exist=True)
    return _json({"generated_at": _now(), "compose_file": str(path), "result": _run(_cmd("docker") + ["compose", "-p", project_name, "-f", str(path), "config"], timeout=60, tool_name="docker_compose_plan")})


@tool("docker_compose_apply", parse_docstring=True)
def docker_compose_apply_tool(compose_file: str = "docker/docker-compose-dev.yaml", project_name: str = "octoagent-dev", action: str = "up", confirmed_by_user: bool = False) -> str:
    """Apply a Docker Compose action after explicit approval.

    Args:
        compose_file: Compose file path.
        project_name: Compose project name.
        action: up, down, restart, pull, or build.
        confirmed_by_user: Must be true after user approval.
    """
    msg = _require_confirmation(confirmed_by_user, f"docker compose {action}")
    if msg:
        return msg
    path = _resolve_path(compose_file, must_exist=True)
    action = action.strip().lower()
    if action == "up":
        cmd = _cmd("docker") + ["compose", "-p", project_name, "-f", str(path), "up", "-d", "--remove-orphans"]
    elif action in {"down", "restart", "pull", "build"}:
        cmd = _cmd("docker") + ["compose", "-p", project_name, "-f", str(path), action]
    else:
        return _json({"error": "unsupported action", "allowed": ["up", "down", "restart", "pull", "build"]})
    return _json({"generated_at": _now(), "result": _run(cmd, timeout=1800, tool_name="docker_compose_apply")})


@tool("ssh_hosts_list", parse_docstring=True)
def ssh_hosts_list_tool() -> str:
    """List configured SSH hosts from the current user's SSH config."""
    config = Path.home() / ".ssh" / "config"
    hosts: list[str] = []
    if config.exists():
        for line in config.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0].lower() == "host" and "*" not in parts[1]:
                hosts.extend(parts[1:])
    return _json({"generated_at": _now(), "config": str(config), "hosts": sorted(set(hosts))})


@tool("ssh_probe", parse_docstring=True)
def ssh_probe_tool(host: str, timeout_seconds: int = 10) -> str:
    """Probe non-interactive SSH connectivity to a configured host.

    Args:
        host: SSH host alias or hostname.
        timeout_seconds: Connect timeout.
    """
    bounded_timeout = max(1, min(int(timeout_seconds), 60))
    return _json(
        {
            "generated_at": _now(),
            "host": host,
            "result": _run(
                _cmd("ssh") + ["-o", "BatchMode=yes", "-o", f"ConnectTimeout={bounded_timeout}", host, "true"],
                timeout=max(5, min(bounded_timeout + 5, 70)),
                tool_name="ssh_probe",
            ),
        }
    )


@tool("ssh_exec", parse_docstring=True)
def ssh_exec_tool(host: str, command: str, timeout_seconds: int = 120, confirmed_by_user: bool = False) -> str:
    """Run a non-interactive command on an SSH host after approval.

    Args:
        host: SSH host alias or hostname.
        command: Remote shell command.
        timeout_seconds: Execution timeout.
        confirmed_by_user: Must be true after user approval.
    """
    msg = _require_confirmation(confirmed_by_user, f"ssh_exec {host}")
    if msg:
        return msg
    return _json({"generated_at": _now(), "host": host, "result": _run(_cmd("ssh") + ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", host, command], timeout=max(5, min(int(timeout_seconds), 3600)), tool_name="ssh_exec")})


@tool("ssh_copy", parse_docstring=True)
def ssh_copy_tool(source: str, destination: str, recursive: bool = False, confirmed_by_user: bool = False) -> str:
    """Copy files with scp after approval.

    Args:
        source: Local or remote source path.
        destination: Local or remote destination path.
        recursive: Copy directories recursively.
        confirmed_by_user: Must be true after user approval.
    """
    msg = _require_confirmation(confirmed_by_user, f"scp {source} {destination}")
    if msg:
        return msg
    args = _cmd("scp") + ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
    if recursive:
        args.append("-r")
    args.extend([source, destination])
    return _json({"generated_at": _now(), "result": _run(args, timeout=1800, tool_name="ssh_copy")})


@tool("git_status", parse_docstring=True)
def git_status_tool(repo: str = ".") -> str:
    """Show git status for a repository.

    Args:
        repo: Repository path.
    """
    path = _resolve_path(repo, must_exist=True)
    return _json({"generated_at": _now(), "repo": str(path), "result": _run(_cmd("git") + ["status", "--short", "--branch"], cwd=path, timeout=20, tool_name="git_status")})


@tool("git_diff", parse_docstring=True)
def git_diff_tool(repo: str = ".", staged: bool = False, pathspec: str = "") -> str:
    """Show git diff.

    Args:
        repo: Repository path.
        staged: Show staged diff.
        pathspec: Optional pathspec.
    """
    path = _resolve_path(repo, must_exist=True)
    args = _cmd("git") + ["diff", "--stat"]
    if staged:
        args.append("--cached")
    if pathspec.strip():
        args.extend(["--", pathspec.strip()])
    stat = _run(args, cwd=path, timeout=30, tool_name="git_diff")
    args2 = _cmd("git") + ["diff"] + (["--cached"] if staged else [])
    if pathspec.strip():
        args2.extend(["--", pathspec.strip()])
    full = _run(args2, cwd=path, timeout=60, tool_name="git_diff")
    return _json({"generated_at": _now(), "repo": str(path), "stat": stat, "diff": full})


@tool("git_log", parse_docstring=True)
def git_log_tool(repo: str = ".", max_count: int = 20) -> str:
    """Show recent git commits.

    Args:
        repo: Repository path.
        max_count: Maximum commits.
    """
    path = _resolve_path(repo, must_exist=True)
    return _json({"generated_at": _now(), "repo": str(path), "result": _run(_cmd("git") + ["log", "--oneline", "--decorate", f"-{max(1, min(int(max_count), 200))}"], cwd=path, timeout=30, tool_name="git_log")})


@tool("git_branch", parse_docstring=True)
def git_branch_tool(repo: str = ".", all_branches: bool = False) -> str:
    """List git branches.

    Args:
        repo: Repository path.
        all_branches: Include remote branches.
    """
    path = _resolve_path(repo, must_exist=True)
    args = _cmd("git") + ["branch"] + (["--all"] if all_branches else [])
    return _json({"generated_at": _now(), "repo": str(path), "result": _run(args, cwd=path, timeout=30, tool_name="git_branch")})


@tool("git_fetch", parse_docstring=True)
def git_fetch_tool(repo: str = ".", remote: str = "origin", prune: bool = True, confirmed_by_user: bool = False) -> str:
    """Fetch a git remote after approval.

    Args:
        repo: Repository path.
        remote: Remote name.
        prune: Include --prune.
        confirmed_by_user: Must be true after user approval.
    """
    msg = _require_confirmation(confirmed_by_user, f"git fetch {remote}")
    if msg:
        return msg
    path = _resolve_path(repo, must_exist=True)
    args = _cmd("git") + ["fetch", remote]
    if prune:
        args.append("--prune")
    return _json({"generated_at": _now(), "repo": str(path), "result": _run(args, cwd=path, timeout=600, tool_name="git_fetch")})


@tool("git_apply_patch", parse_docstring=True)
def git_apply_patch_tool(repo: str, patch_text: str, check_only: bool = True, confirmed_by_user: bool = False) -> str:
    """Apply or check a unified git patch after approval.

    Args:
        repo: Repository path.
        patch_text: Unified diff text.
        check_only: Only check whether the patch applies.
        confirmed_by_user: Must be true when check_only is false.
    """
    if not check_only:
        msg = _require_confirmation(confirmed_by_user, "git apply patch")
        if msg:
            return msg
    path = _resolve_path(repo, must_exist=True)
    patch_file = _artifact_dir("git_apply_patch") / "pending.patch"
    patch_file.write_text(patch_text, encoding="utf-8")
    args = _cmd("git") + ["apply", "--check" if check_only else str(patch_file)]
    if check_only:
        args.append(str(patch_file))
    return _json({"generated_at": _now(), "repo": str(path), "patch_file": str(patch_file), "result": _run(args, cwd=path, timeout=120, tool_name="git_apply_patch")})


@tool("git_commit_prepare", parse_docstring=True)
def git_commit_prepare_tool(repo: str = ".") -> str:
    """Prepare a commit summary without creating a commit.

    Args:
        repo: Repository path.
    """
    path = _resolve_path(repo, must_exist=True)
    return _json(
        {
            "generated_at": _now(),
            "repo": str(path),
            "status": _run(
                _cmd("git") + ["status", "--short"],
                cwd=path,
                timeout=20,
                tool_name="git_commit_prepare",
            ),
            "stat": _run(
                _cmd("git") + ["diff", "--stat", "HEAD"],
                cwd=path,
                timeout=30,
                tool_name="git_commit_prepare",
            ),
        }
    )


@tool("db_connect_check", parse_docstring=True)
def db_connect_check_tool(dsn: str = _DEFAULT_DB_DSN, timeout_seconds: int = 5) -> str:
    """Check PostgreSQL connectivity.

    Args:
        dsn: PostgreSQL DSN.
        timeout_seconds: Statement timeout.
    """
    sql = f"set statement_timeout={max(1000, min(int(timeout_seconds) * 1000, 60000))}; select current_user, current_database(), version();"
    return _json({"generated_at": _now(), "result": _run(_cmd("psql") + [dsn, "-v", "ON_ERROR_STOP=1", "-X", "-Atc", sql], timeout=max(5, min(int(timeout_seconds) + 5, 70)), tool_name="db_connect_check")})


@tool("db_query_readonly", parse_docstring=True)
def db_query_readonly_tool(sql: str, dsn: str = _DEFAULT_DB_DSN, row_limit: int = 100, timeout_seconds: int = 10) -> str:
    """Run one read-only PostgreSQL query with timeout and row limit.

    Args:
        sql: SELECT/WITH/SHOW query. Multiple statements and writes are rejected.
        dsn: PostgreSQL DSN.
        row_limit: Maximum rows returned.
        timeout_seconds: Statement timeout.
    """
    error = _safe_db_query(sql)
    if error:
        return _json({"error": error})
    limit = max(1, min(int(row_limit), 1000))
    wrapped = f"set statement_timeout={max(1000, min(int(timeout_seconds) * 1000, 60000))}; with q as ({sql.strip().rstrip(';')}) select * from q limit {limit};"
    return _json({"generated_at": _now(), "row_limit": limit, "result": _run(_cmd("psql") + [dsn, "-v", "ON_ERROR_STOP=1", "-X", "--csv", "-c", wrapped], timeout=max(5, min(int(timeout_seconds) + 5, 70)), tool_name="db_query_readonly")})


@tool("db_schema_introspect", parse_docstring=True)
def db_schema_introspect_tool(dsn: str = _DEFAULT_DB_DSN, schema_name: str = "public", table_pattern: str = "%", row_limit: int = 200) -> str:
    """Inspect PostgreSQL schema tables and columns.

    Args:
        dsn: PostgreSQL DSN.
        schema_name: Schema name.
        table_pattern: SQL LIKE pattern for table names.
        row_limit: Maximum rows.
    """
    sql = "select table_schema, table_name, column_name, data_type from information_schema.columns where table_schema = :'schema' and table_name like :'pattern' order by table_schema, table_name, ordinal_position limit :limit"
    limit = max(1, min(int(row_limit), 1000))
    return _json(
        {
            "generated_at": _now(),
            "result": _run(
                _cmd("psql")
                + [
                    dsn,
                    "-X",
                    "--csv",
                    "-v",
                    f"schema={schema_name}",
                    "-v",
                    f"pattern={table_pattern}",
                    "-v",
                    f"limit={limit}",
                    "-c",
                    sql,
                ],
                timeout=20,
                tool_name="db_schema_introspect",
            ),
        }
    )


@tool("db_explain", parse_docstring=True)
def db_explain_tool(sql: str, dsn: str = _DEFAULT_DB_DSN, timeout_seconds: int = 10) -> str:
    """Explain a read-only PostgreSQL query without executing writes.

    Args:
        sql: SELECT/WITH query.
        dsn: PostgreSQL DSN.
        timeout_seconds: Statement timeout.
    """
    error = _safe_db_query(sql)
    if error:
        return _json({"error": error})
    statement = f"set statement_timeout={max(1000, min(int(timeout_seconds) * 1000, 60000))}; explain (format json) {sql.strip().rstrip(';')}"
    return _json({"generated_at": _now(), "result": _run(_cmd("psql") + [dsn, "-v", "ON_ERROR_STOP=1", "-X", "-c", statement], timeout=max(5, min(int(timeout_seconds) + 5, 70)), tool_name="db_explain")})


@tool("db_migration_plan", parse_docstring=True)
def db_migration_plan_tool(migration_sql: str, dsn: str = _DEFAULT_DB_DSN) -> str:
    """Analyze a migration SQL string and produce a risk plan without applying it.

    Args:
        migration_sql: Migration SQL text.
        dsn: PostgreSQL DSN for optional connectivity context.
    """
    statements = [s.strip() for s in migration_sql.split(";") if s.strip()]
    risks = []
    for idx, statement in enumerate(statements, 1):
        kind = statement.split(None, 1)[0].lower() if statement.split() else "unknown"
        destructive = bool(re.search(r"\b(drop|truncate|delete|alter\s+table.*drop|update)\b", statement, re.I))
        risks.append({"index": idx, "kind": kind, "destructive": destructive, "preview": statement[:300]})
    return _json(
        {
            "generated_at": _now(),
            "dsn_connectivity": _run(
                _cmd("psql") + [dsn, "-X", "-Atc", "select current_database(), current_user"],
                timeout=5,
                tool_name="db_migration_plan",
            ),
            "statement_count": len(statements),
            "requires_write_approval": True,
            "risks": risks,
        }
    )


@tool("secret_scan", parse_docstring=True)
def secret_scan_tool(root: str = ".", max_files: int = 5000, max_findings: int = 200) -> str:
    """Scan text files for likely secrets and save full findings as an artifact.

    Args:
        root: Root path to scan.
        max_files: Maximum files.
        max_findings: Maximum findings.
    """
    root_path = _resolve_path(root, must_exist=True)
    findings = []
    scanned = 0
    skipped = {".git", "node_modules", ".venv", "__pycache__", ".next", "runtime/cache"}
    for current, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in skipped]
        for name in files:
            if scanned >= max(1, min(int(max_files), 50000)):
                break
            path = Path(current) / name
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".pyc", ".sqlite", ".db"}:
                continue
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")[:1_000_000]
            except Exception:
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                for typ, pattern in _SECRET_PATTERNS:
                    if pattern.search(line):
                        findings.append({"type": typ, "file": str(path), "line": line_no})
                        if len(findings) >= max(1, min(int(max_findings), 1000)):
                            artifact = _write_artifact("secret_scan", "findings", json.dumps(findings, ensure_ascii=False, indent=2))
                            return _json({"generated_at": _now(), "root": str(root_path), "scanned_files": scanned, "finding_count": len(findings), "truncated": True, "artifact": artifact, "findings_preview": findings[:20]})
    artifact = _write_artifact("secret_scan", "findings", json.dumps(findings, ensure_ascii=False, indent=2))
    return _json({"generated_at": _now(), "root": str(root_path), "scanned_files": scanned, "finding_count": len(findings), "truncated": False, "artifact": artifact, "findings_preview": findings[:20]})


@tool("dependency_audit", parse_docstring=True)
def dependency_audit_tool(scope: str = "all") -> str:
    """Run available dependency audit commands and save full logs.

    Args:
        scope: all, python, or frontend.
    """
    scope = scope.strip().lower()
    results = {}
    if scope in {"all", "python"}:
        if (_REPO_ROOT / "backend" / "requirements.txt").exists():
            results["pip_audit_available"] = _which("pip-audit") is not None
            cmd = [_which("pip-audit"), "-r", "backend/requirements.txt"] if _which("pip-audit") else [_backend_python(), "-m", "pip", "check"]
            results["python"] = _run(cmd, cwd=_REPO_ROOT, timeout=600, tool_name="dependency_audit")
    if scope in {"all", "frontend"} and (_FRONTEND_ROOT / "package.json").exists():
        package_manager = _which("pnpm") or _which("npm") or "npm"
        cmd = [package_manager, "audit", "--json"] if Path(package_manager).name == "pnpm" else [package_manager, "audit", "--json"]
        results["frontend"] = _run(cmd, cwd=_FRONTEND_ROOT, timeout=600, tool_name="dependency_audit")
    return _json({"generated_at": _now(), "scope": scope, "results": results})


@tool("static_security_scan", parse_docstring=True)
def static_security_scan_tool(root: str = "backend/src", timeout_seconds: int = 900) -> str:
    """Run backend-venv-compatible static security checks.

    Combines Ruff security (S) rules and Bandit when available.

    Args:
        root: Path to scan.
        timeout_seconds: Timeout.
    """
    path = _resolve_path(root, must_exist=True)
    timeout = max(60, min(int(timeout_seconds), 3600))
    results = {
        "ruff_security": _run([_backend_python(), "-m", "ruff", "check", "--select", "S", str(path)], timeout=timeout, tool_name="static_security_scan"),
    }
    bandit = _which("bandit")
    if bandit:
        results["bandit"] = _run([bandit, "-r", str(path), "-f", "json"], timeout=timeout, tool_name="static_security_scan")
    else:
        results["bandit"] = {"available": False, "error": "bandit is not installed in backend/.venv"}
    return _json({"generated_at": _now(), "results": results})


@tool("bandit_scan", parse_docstring=True)
def bandit_scan_tool(root: str = "backend/src", timeout_seconds: int = 600) -> str:
    """Run bandit Python security scan.

    Args:
        root: Path to scan.
        timeout_seconds: Timeout.
    """
    path = _resolve_path(root, must_exist=True)
    exe = _which("bandit")
    if not exe:
        return _json({"error": "bandit not installed in backend/.venv", "install": "scripts/tools/install-system-tools.sh python-security"})
    return _json({"generated_at": _now(), "result": _run([exe, "-r", str(path), "-f", "json"], timeout=max(60, min(int(timeout_seconds), 3600)), tool_name="bandit_scan")})


@tool("trivy_scan", parse_docstring=True)
def trivy_scan_tool(root: str = ".", scan_type: str = "fs", timeout_seconds: int = 900) -> str:
    """Run Trivy filesystem/config scan.

    Args:
        root: Path to scan.
        scan_type: fs or config.
        timeout_seconds: Timeout.
    """
    path = _resolve_path(root, must_exist=True)
    exe = _which("trivy")
    if not exe:
        return _json({"error": "trivy not installed in runtime/tools/bin", "install": "scripts/tools/install-system-tools.sh trivy"})
    mode = "config" if scan_type.strip().lower() == "config" else "fs"
    return _json({"generated_at": _now(), "result": _run([exe, mode, "--format", "json", str(path)], timeout=max(60, min(int(timeout_seconds), 3600)), tool_name="trivy_scan")})


@tool("pytest_collect", parse_docstring=True)
def pytest_collect_tool(path: str = "backend", timeout_seconds: int = 300) -> str:
    """Collect pytest tests without running them.

    Args:
        path: Test path.
        timeout_seconds: Timeout.
    """
    target = _resolve_path(path, default=_REPO_ROOT, must_exist=True)
    return _json({"generated_at": _now(), "result": _run([_backend_python(), "-m", "pytest", "--collect-only", "-q", str(target)], cwd=_REPO_ROOT, timeout=max(30, min(int(timeout_seconds), 1800)), tool_name="pytest_collect")})


@tool("pytest_run", parse_docstring=True)
def pytest_run_tool(path: str = "backend", keyword: str = "", timeout_seconds: int = 900) -> str:
    """Run pytest with optional path and keyword filter.

    Args:
        path: Test path or node id.
        keyword: Optional pytest -k expression.
        timeout_seconds: Timeout.
    """
    args = [_backend_python(), "-m", "pytest", str(_resolve_path(path, default=_REPO_ROOT, must_exist=False))]
    if keyword.strip():
        args.extend(["-k", keyword.strip()])
    return _json({"generated_at": _now(), "result": _run(args, cwd=_REPO_ROOT, timeout=max(60, min(int(timeout_seconds), 7200)), tool_name="pytest_run")})


@tool("playwright_run", parse_docstring=True)
def playwright_run_tool(project: str = "", grep: str = "", timeout_seconds: int = 1200) -> str:
    """Run frontend Playwright tests.

    Args:
        project: Optional Playwright project name.
        grep: Optional grep filter.
        timeout_seconds: Timeout.
    """
    package_manager = _which("pnpm") or _which("npm") or "npm"
    args = [package_manager, "exec", "playwright", "test"] if Path(package_manager).name == "pnpm" else [_which("npx") or "npx", "playwright", "test"]
    if project.strip():
        args.extend(["--project", project.strip()])
    if grep.strip():
        args.extend(["--grep", grep.strip()])
    return _json({"generated_at": _now(), "result": _run(args, cwd=_FRONTEND_ROOT, timeout=max(60, min(int(timeout_seconds), 7200)), tool_name="playwright_run")})


@tool("frontend_typecheck", parse_docstring=True)
def frontend_typecheck_tool(timeout_seconds: int = 600) -> str:
    """Run frontend typecheck if package script exists, otherwise tsc noEmit.

    Args:
        timeout_seconds: Timeout.
    """
    package_manager = _which("pnpm") or _which("npm") or "npm"
    package_json = _FRONTEND_ROOT / "package.json"
    scripts = json.loads(package_json.read_text()).get("scripts", {}) if package_json.exists() else {}
    args = [package_manager, "run", "typecheck"] if "typecheck" in scripts else ([package_manager, "exec", "tsc", "--noEmit"] if Path(package_manager).name == "pnpm" else [_which("npx") or "npx", "tsc", "--noEmit"])
    return _json({"generated_at": _now(), "result": _run(args, cwd=_FRONTEND_ROOT, timeout=max(60, min(int(timeout_seconds), 3600)), tool_name="frontend_typecheck")})


@tool("lint_run", parse_docstring=True)
def lint_run_tool(scope: str = "all", timeout_seconds: int = 900) -> str:
    """Run configured backend/frontend linters.

    Args:
        scope: all, backend, or frontend.
        timeout_seconds: Timeout.
    """
    scope = scope.strip().lower()
    results = {}
    if scope in {"all", "backend"}:
        results["backend"] = _run([_backend_python(), "-m", "ruff", "check", "backend/src"], cwd=_REPO_ROOT, timeout=max(60, min(int(timeout_seconds), 3600)), tool_name="lint_run")
    if scope in {"all", "frontend"}:
        package_manager = _which("pnpm") or _which("npm") or "npm"
        package_json = _FRONTEND_ROOT / "package.json"
        scripts = json.loads(package_json.read_text()).get("scripts", {}) if package_json.exists() else {}
        args = [package_manager, "run", "lint"] if "lint" in scripts else ([package_manager, "exec", "next", "lint"] if Path(package_manager).name == "pnpm" else [_which("npx") or "npx", "next", "lint"])
        results["frontend"] = _run(args, cwd=_FRONTEND_ROOT, timeout=max(60, min(int(timeout_seconds), 3600)), tool_name="lint_run")
    return _json({"generated_at": _now(), "scope": scope, "results": results})


_AWESOME_SELFHOSTED_SAAS_TOOLS: list[dict[str, str]] = [
    {
        "name": "Coolify",
        "category": "deployment",
        "description": "Self-hosted PaaS for apps, databases, Docker Compose, and preview deployments.",
        "url": "https://coolify.io/",
        "use_case": "Ship small SaaS services quickly on your own server.",
    },
    {
        "name": "Dokku",
        "category": "deployment",
        "description": "Git-push Heroku-like PaaS built on Docker.",
        "url": "https://dokku.com/",
        "use_case": "Simple single-host app deployment for SaaS MVPs.",
    },
    {
        "name": "CapRover",
        "category": "deployment",
        "description": "Docker-based app platform with one-click apps and web UI.",
        "url": "https://caprover.com/",
        "use_case": "Manage SaaS app, worker, and database services from a UI.",
    },
    {
        "name": "Appwrite",
        "category": "backend",
        "description": "Self-hosted backend platform with auth, database, functions, and storage.",
        "url": "https://appwrite.io/",
        "use_case": "Backend-as-a-service for SaaS prototypes and products.",
    },
    {
        "name": "Supabase",
        "category": "backend",
        "description": "Postgres-based app platform with auth, storage, realtime, and APIs.",
        "url": "https://supabase.com/",
        "use_case": "Postgres-first SaaS backend with managed or self-hosted deployment.",
    },
    {
        "name": "Hasura",
        "category": "api",
        "description": "GraphQL and data API layer for Postgres and other data sources.",
        "url": "https://hasura.io/",
        "use_case": "Expose controlled data APIs for admin panels and SaaS products.",
    },
    {
        "name": "Directus",
        "category": "admin",
        "description": "Data platform and admin UI over SQL databases.",
        "url": "https://directus.io/",
        "use_case": "Internal admin console, CMS, and operator workflows.",
    },
    {
        "name": "Keycloak",
        "category": "auth",
        "description": "Identity and access management with OIDC, SAML, SSO, and realms.",
        "url": "https://www.keycloak.org/",
        "use_case": "Enterprise SaaS authentication, SSO, and tenant identity boundaries.",
    },
    {
        "name": "Zitadel",
        "category": "auth",
        "description": "Cloud-native identity platform with OIDC/OAuth2 and multi-tenant orgs.",
        "url": "https://zitadel.com/",
        "use_case": "Modern SaaS identity provider with org and project concepts.",
    },
    {
        "name": "Ory Kratos",
        "category": "auth",
        "description": "API-first identity and user management service.",
        "url": "https://www.ory.sh/kratos/",
        "use_case": "Custom auth flows when you want identity APIs instead of a monolith.",
    },
    {
        "name": "PostHog",
        "category": "analytics",
        "description": "Product analytics, feature flags, session replay, and experiments.",
        "url": "https://posthog.com/",
        "use_case": "Measure activation, retention, funnels, and feature adoption.",
    },
    {
        "name": "Plausible",
        "category": "analytics",
        "description": "Lightweight privacy-friendly web analytics.",
        "url": "https://plausible.io/",
        "use_case": "Simple traffic analytics for SaaS marketing and docs sites.",
    },
    {
        "name": "Sentry",
        "category": "observability",
        "description": "Error tracking and performance monitoring.",
        "url": "https://sentry.io/",
        "use_case": "Catch frontend/backend exceptions and prioritize production fixes.",
    },
    {
        "name": "Grafana",
        "category": "observability",
        "description": "Metrics dashboards and alerting across many data sources.",
        "url": "https://grafana.com/",
        "use_case": "SaaS service health dashboards and operational alerts.",
    },
    {
        "name": "Uptime Kuma",
        "category": "observability",
        "description": "Self-hosted uptime monitor with status pages.",
        "url": "https://uptime.kuma.pet/",
        "use_case": "External endpoint monitoring and customer-facing status checks.",
    },
    {
        "name": "Lago",
        "category": "billing",
        "description": "Open-source metering and billing platform.",
        "url": "https://www.getlago.com/",
        "use_case": "Usage-based SaaS billing and invoice workflows.",
    },
    {
        "name": "Kill Bill",
        "category": "billing",
        "description": "Subscription billing and payments platform.",
        "url": "https://killbill.io/",
        "use_case": "Complex subscription, invoicing, and payment workflows.",
    },
    {
        "name": "Chatwoot",
        "category": "support",
        "description": "Customer support inbox and live chat platform.",
        "url": "https://www.chatwoot.com/",
        "use_case": "Support conversations, in-app chat, and shared inboxes.",
    },
    {
        "name": "Listmonk",
        "category": "email",
        "description": "Newsletter and mailing list manager.",
        "url": "https://listmonk.app/",
        "use_case": "Product updates, lifecycle emails, and audience lists.",
    },
    {
        "name": "n8n",
        "category": "automation",
        "description": "Workflow automation platform with many integrations.",
        "url": "https://n8n.io/",
        "use_case": "Automate SaaS back-office workflows and webhooks.",
    },
    {
        "name": "MinIO",
        "category": "storage",
        "description": "S3-compatible object storage.",
        "url": "https://min.io/",
        "use_case": "Tenant files, backups, exports, and media storage.",
    },
    {
        "name": "Gitea",
        "category": "devops",
        "description": "Lightweight Git forge with issues, pull requests, and packages.",
        "url": "https://gitea.com/",
        "use_case": "Self-host source control for SaaS engineering teams.",
    },
    {
        "name": "Plane",
        "category": "project",
        "description": "Project and product planning tool.",
        "url": "https://plane.so/",
        "use_case": "Roadmaps, issues, cycles, and SaaS product planning.",
    },
]


_AWESOME_CATALOG_PATH = _REPO_ROOT / "runtime" / "catalogs" / "awesome-selfhosted-saas.json"


def _load_awesome_selfhosted_catalog() -> dict[str, Any]:
    fallback = {
        "version": "static-fallback",
        "source": "curated awesome-selfhosted-style SaaS development catalog",
        "tools": _AWESOME_SELFHOSTED_SAAS_TOOLS,
        "task_templates": [],
    }
    if not _AWESOME_CATALOG_PATH.exists():
        return fallback
    try:
        data = json.loads(_AWESOME_CATALOG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("tools"), list):
            return fallback
        return data
    except Exception:
        return fallback


@tool("awesome_selfhosted", parse_docstring=True)
def awesome_selfhosted_tool(query: str = "", category: str = "", max_results: int = 20, template: str = "") -> str:
    """Find self-hosted SaaS development tools from a curated awesome-selfhosted-style catalog.

    Args:
        query: Optional keyword filter across name, description, and use case.
        category: Optional category filter such as deployment, backend, auth, billing, analytics, observability, support, email, automation, storage, devops, or project.
        max_results: Maximum number of tools to return.
        template: Optional task template id such as create_saas, connect_auth, connect_billing, deploy_compose, or security_baseline.
    """
    catalog = _load_awesome_selfhosted_catalog()
    tools = [item for item in catalog.get("tools", []) if isinstance(item, dict)]
    templates = [item for item in catalog.get("task_templates", []) if isinstance(item, dict)]
    needle = query.strip().lower()
    category_filter = category.strip().lower()
    template_filter = template.strip().lower()
    limit = max(1, min(int(max_results), 50))
    categories = sorted({str(item.get("category", "")) for item in tools if str(item.get("category", "")).strip()})
    results = []
    for item in tools:
        haystack = " ".join(str(value) for value in item.values()).lower()
        if category_filter and str(item.get("category", "")).lower() != category_filter:
            continue
        if needle and needle not in haystack:
            continue
        results.append(item)
        if len(results) >= limit:
            break
    selected_templates = []
    for item in templates:
        item_id = str(item.get("id", "")).lower()
        if template_filter and item_id != template_filter:
            continue
        if category_filter and category_filter not in [str(cat).lower() for cat in item.get("recommended_categories", [])]:
            continue
        selected_templates.append(item)
    return _json(
        {
            "generated_at": _now(),
            "source": catalog.get("source", "curated awesome-selfhosted SaaS catalog"),
            "catalog_version": catalog.get("version"),
            "catalog_path": str(_AWESOME_CATALOG_PATH),
            "query": query,
            "category": category,
            "template": template,
            "available_categories": categories,
            "count": len(results),
            "results": results,
            "task_templates": selected_templates,
        }
    )


@tool("octo_doctor", parse_docstring=True)
def octo_doctor_tool(include_repairs: bool = False) -> str:
    """Unified OctoAgent doctor for MCP, skills, hooks, plugins, RAG, tools, and services.

    Args:
        include_repairs: If true, perform safe repair checks only; destructive repairs still require separate system approval tools.
    """
    checks: dict[str, Any] = {}
    checks["services"] = {svc: _run(["systemctl", "is-active", svc], timeout=5, tool_name="octo_doctor", artifact=False) for svc in ("octoagent-local.service", "llamacpp.service", "mihomo.service")}
    checks["binaries"] = {name: _which(name) for name in ("npx", "node", "docker", "git", "ssh", "psql", "sqlite3", "pytest", "ruff", "bandit", "trivy")}
    checks["tool_policy"] = {"backend_venv": str(_BACKEND_VENV_BIN), "managed_bin": str(_MANAGED_BIN), "node_tools_bin": str(_NODE_TOOLS_BIN)}
    cfg_path = _REPO_ROOT / "extensions_config.json"
    if cfg_path.exists():
        data = json.loads(cfg_path.read_text())
        mcp = data.get("mcpServers", {})
        checks["mcp"] = {
            name: {
                "enabled": bool(cfg.get("enabled")),
                "command": cfg.get("command"),
                "resolved_command": _resolve_mcp_command(str(cfg.get("command") or "")),
                "permissionScope": cfg.get("permissionScope", "sandbox"),
                "missing_command": _mcp_command_missing(cfg),
            }
            for name, cfg in mcp.items()
        }
        checks["skills"] = {"configured": len(data.get("skills", {})), "enabled": sum(1 for v in data.get("skills", {}).values() if v.get("enabled", True))}
        checks["hooks"] = {"configured": len(data.get("hooks", {})), "enabled": sum(1 for v in data.get("hooks", {}).values() if v.get("enabled", True))}
    checks["plugins_api"] = _run(_cmd("curl") + ["-sS", "--max-time", "5", "http://127.0.0.1:19802/api/tools/registry"], timeout=8, tool_name="octo_doctor", artifact=False)
    checks["rag_dirs"] = {"runtime": str(_REPO_ROOT / "runtime"), "storage_exists": (_REPO_ROOT / "backend" / "src" / "storage" / "rag").exists()}
    if include_repairs:
        checks["repair_note"] = "Safe checks completed. Use specific system tools with chat approval for service restarts, installs, Docker/SSH/Git writes, or database migrations."
    return _json({"generated_at": _now(), "checks": checks})


SYSTEM_EXTRA_TOOLS = [
    docker_status_tool,
    docker_ps_tool,
    docker_images_tool,
    docker_logs_tool,
    docker_inspect_tool,
    docker_compose_plan_tool,
    docker_compose_apply_tool,
    ssh_hosts_list_tool,
    ssh_probe_tool,
    ssh_exec_tool,
    ssh_copy_tool,
    git_status_tool,
    git_diff_tool,
    git_log_tool,
    git_branch_tool,
    git_fetch_tool,
    git_apply_patch_tool,
    git_commit_prepare_tool,
    db_connect_check_tool,
    db_query_readonly_tool,
    db_schema_introspect_tool,
    db_explain_tool,
    db_migration_plan_tool,
    secret_scan_tool,
    dependency_audit_tool,
    static_security_scan_tool,
    bandit_scan_tool,
    trivy_scan_tool,
    pytest_collect_tool,
    pytest_run_tool,
    playwright_run_tool,
    frontend_typecheck_tool,
    lint_run_tool,
    awesome_selfhosted_tool,
    octo_doctor_tool,
]
