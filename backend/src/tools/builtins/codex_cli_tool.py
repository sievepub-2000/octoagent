from __future__ import annotations

import shlex
import shutil
import subprocess
import time
from pathlib import Path

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]

from src.gateway.observability import record_exception_trace, record_tool_trace
from src.runtime.config.paths import get_paths
from src.runtime.governance import get_runtime_worker_isolation


@tool("codex_cli", parse_docstring=True)
def codex_cli_tool(
    command: str,
    cwd: str | None = None,
    timeout_seconds: int = 120,
) -> str:
    """Run OpenAI Codex CLI command on the server host.

    Args:
        command: Codex CLI arguments string (example: "--help" or "exec --help").
        cwd: Optional working directory. Defaults to project workspace root.
        timeout_seconds: Execution timeout in seconds. Values below 5 are raised to 5;
            no upper clamp is applied so long-running delegated CLI work can opt in explicitly.
    """
    codex_bin = shutil.which("codex")
    if codex_bin is None:
        return "Error: codex CLI is not installed or not in PATH on this server."

    workspace_root = get_paths().base_dir
    target_cwd = Path(cwd).expanduser() if cwd else workspace_root
    if not target_cwd.exists() or not target_cwd.is_dir():
        return f"Error: invalid cwd '{target_cwd}'."

    safe_timeout = max(5, int(timeout_seconds))

    args = [codex_bin]
    if command.strip():
        args.extend(shlex.split(command))

    started = time.monotonic()
    record_tool_trace("subprocess_start", tool="codex_cli", args=args, cwd=str(target_cwd), timeout=safe_timeout)
    try:
        with get_runtime_worker_isolation().slot("system"):
            result = subprocess.run(
                args,
                cwd=str(target_cwd),
                capture_output=True,
                text=True,
                timeout=safe_timeout,
                check=False,
            )
    except subprocess.TimeoutExpired:
        record_tool_trace("subprocess_timeout", tool="codex_cli", args=args, cwd=str(target_cwd), timeout=safe_timeout)
        return f"Error: codex command timed out after {safe_timeout}s."
    except Exception as exc:
        record_exception_trace("codex_cli_tool", exc, args=args, cwd=str(target_cwd), timeout=safe_timeout)
        return f"Error: failed to run codex CLI: {exc}"

    record_tool_trace(
        "subprocess_end",
        tool="codex_cli",
        args=args,
        cwd=str(target_cwd),
        exit_code=result.returncode,
        duration_ms=round((time.monotonic() - started) * 1000, 3),
        stdout_preview=(result.stdout or "")[-1200:],
        stderr_preview=(result.stderr or "")[-1200:],
    )

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    combined: list[str] = []
    combined.append(f"exit_code={result.returncode}")
    if stdout:
        combined.append("stdout:\n" + stdout)
    if stderr:
        combined.append("stderr:\n" + stderr)
    return "\n\n".join(combined)
