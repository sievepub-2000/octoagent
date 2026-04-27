from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]

from src.config.paths import get_paths


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
        timeout_seconds: Execution timeout in seconds (5-900).
    """
    codex_bin = shutil.which("codex")
    if codex_bin is None:
        return "Error: codex CLI is not installed or not in PATH on this server."

    workspace_root = get_paths().base_dir
    target_cwd = Path(cwd).expanduser() if cwd else workspace_root
    if not target_cwd.exists() or not target_cwd.is_dir():
        return f"Error: invalid cwd '{target_cwd}'."

    safe_timeout = max(5, min(timeout_seconds, 900))

    args = [codex_bin]
    if command.strip():
        args.extend(shlex.split(command))

    try:
        result = subprocess.run(
            args,
            cwd=str(target_cwd),
            capture_output=True,
            text=True,
            timeout=safe_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"Error: codex command timed out after {safe_timeout}s."
    except Exception as exc:
        return f"Error: failed to run codex CLI: {exc}"

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    combined: list[str] = []
    combined.append(f"exit_code={result.returncode}")
    if stdout:
        combined.append("stdout:\n" + stdout)
    if stderr:
        combined.append("stderr:\n" + stderr)
    return "\n\n".join(combined)
