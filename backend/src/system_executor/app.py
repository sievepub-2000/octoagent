from __future__ import annotations

import asyncio
import hmac
import os
import shlex
import socket
import subprocess
import time
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    command: str = Field(min_length=1, max_length=200_000)
    cwd: str = Field(default="/", min_length=1, max_length=4096)
    timeout_seconds: int = Field(default=120, ge=1, le=3600)


app = FastAPI(title="OctoAgent System Executor", docs_url=None, redoc_url=None)
_execution_lock = asyncio.Lock()


def _configured_token() -> str:
    token = os.environ.get("OCTOAGENT_SYSTEM_EXECUTOR_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError("OCTOAGENT_SYSTEM_EXECUTOR_TOKEN must contain at least 32 characters")
    return token


def _authorize(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = f"Bearer {_configured_token()}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


def _execute_on_host(request: ExecuteRequest) -> dict[str, object]:
    if "\x00" in request.command or "\x00" in request.cwd:
        raise ValueError("NUL bytes are not allowed")
    if not request.cwd.startswith("/"):
        raise ValueError("cwd must be an absolute host path")

    backend_image = os.environ.get("OCTOAGENT_BACKEND_IMAGE", "octoagent/backend:local")
    host_script = f"cd -- {shlex.quote(request.cwd)} && {request.command}"
    command = [
        "/usr/local/bin/docker",
        "run",
        "--rm",
        "--privileged",
        "--pid=host",
        "--network=host",
        "--user=0",
        "--add-host=host.docker.internal:host-gateway",
        "--volume=/:/host:rw",
    ]
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"):
        value = os.environ.get(key, "").strip()
        if key.lower() in {"http_proxy", "https_proxy"} and "host.docker.internal" in value:
            try:
                host_gateway = socket.gethostbyname("host.docker.internal")
                value = value.replace("host.docker.internal", host_gateway)
            except OSError:
                pass
        if value:
            command.extend(["--env", f"{key}={value}"])
    command.extend([backend_image, "chroot", "/host", "/bin/bash", "-lc", host_script])
    started = time.monotonic()
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=request.timeout_seconds + 30,
        check=False,
    )
    return {
        "exit_code": result.returncode,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
        "cwd": request.cwd,
    }


@app.get("/health")
async def health() -> dict[str, object]:
    token_ready = len(os.environ.get("OCTOAGENT_SYSTEM_EXECUTOR_TOKEN", "")) >= 32
    socket_ready = os.path.exists("/var/run/docker.sock")
    if not token_ready or not socket_ready:
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "token_ready": token_ready, "docker_socket": socket_ready},
        )
    return {"status": "healthy", "token_ready": True, "docker_socket": True}


@app.post("/execute", dependencies=[Depends(_authorize)])
async def execute(request: ExecuteRequest) -> dict[str, object]:
    async with _execution_lock:
        try:
            return await asyncio.to_thread(_execute_on_host, request)
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail=f"host command timed out after {request.timeout_seconds}s") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"host execution failed: {type(exc).__name__}: {exc}") from exc
