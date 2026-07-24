"""Run quick release prechecks for local OctoAgent development."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class StepResult:
    name: str
    command: str
    returncode: int
    seconds: float


_BACKEND_RUFF_TARGETS = [
    "src",
    "scripts",
]


def _format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _run_step(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
) -> StepResult:
    rendered = _format_command(command)
    print(f"[precheck] {name}")
    print(f"[precheck] $ {rendered}")
    started = time.monotonic()
    result = subprocess.run(command, cwd=cwd, env=env, check=False)
    elapsed = round(time.monotonic() - started, 2)
    print(f"[precheck] -> rc={result.returncode} ({elapsed}s)")
    return StepResult(
        name=name,
        command=rendered,
        returncode=result.returncode,
        seconds=elapsed,
    )


def _frontend_package_manager_base() -> list[str]:
    if shutil.which("pnpm"):
        return ["pnpm"]
    if shutil.which("corepack"):
        return ["corepack", "pnpm"]
    raise RuntimeError("pnpm is required for frontend release precheck")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run smoke + key regression checks before release commit/push.",
    )
    parser.add_argument(
        "--frontend-url",
        default="http://127.0.0.1:19800",
        help="Frontend URL used by smoke test (default: http://127.0.0.1:19800).",
    )
    parser.add_argument(
        "--gateway-url",
        default="http://127.0.0.1:19800",
        help="Gateway URL used by smoke test (default: http://127.0.0.1:19800).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="HTTP/API timeout passed to smoke test (default: 30).",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run smoke route with ?mock=true.",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip WebUI/API smoke step.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    backend_root = Path(__file__).resolve().parents[1]
    frontend_root = backend_root.parent / "frontend"
    python_bin = backend_root / ".venv/bin/python"
    if not python_bin.exists():
        python_bin = Path(sys.executable)
    frontend_pm = _frontend_package_manager_base()

    steps: list[StepResult] = []

    steps.append(
        _run_step(
            name="compileall backend source and regression assets",
            command=[
                str(python_bin),
                "-m",
                "compileall",
                "-q",
                "src",
                "scripts",
            ],
            cwd=backend_root,
        )
    )

    steps.append(
        _run_step(
            name="verify uv dependency lock with bounded resolver",
            command=["timeout", "600s", "uv", "lock", "--locked"],
            cwd=backend_root,
        )
    )

    steps.append(
        _run_step(
            name="ruff lint backend release surfaces",
            command=[str(python_bin), "-m", "ruff", "check", *_BACKEND_RUFF_TARGETS],
            cwd=backend_root,
        )
    )

    steps.append(
        _run_step(
            name="bounded long-running runtime soak",
            command=[
                str(python_bin),
                "scripts/run_long_running_soak.py",
                "--iterations",
                "40",
                "--duration-seconds",
                "5",
                "--sample-interval-seconds",
                "2",
            ],
            cwd=backend_root,
        )
    )

    steps.append(
        _run_step(
            name="system doctor and core API contract smoke",
            command=[str(python_bin), "scripts/run_system_doctor.py", "--skip-git"],
            cwd=backend_root,
        )
    )

    steps.append(
        _run_step(
            name="system execution operator auth smoke",
            command=[str(python_bin), "scripts/run_system_execution_security_smoke.py"],
            cwd=backend_root,
        )
    )

    steps.append(
        _run_step(
            name="release readiness evidence manifest contract smoke",
            command=[str(python_bin), "scripts/run_release_readiness_contract_smoke.py"],
            cwd=backend_root,
        )
    )

    steps.append(
        _run_step(
            name="pnpm install frontend dependencies",
            command=[*frontend_pm, "install", "--frozen-lockfile"],
            cwd=frontend_root,
        )
    )
    steps.append(
        _run_step(
            name="pnpm lint frontend",
            command=[*frontend_pm, "lint"],
            cwd=frontend_root,
        )
    )
    steps.append(
        _run_step(
            name="pnpm build frontend",
            command=[*frontend_pm, "run", "build"],
            cwd=frontend_root,
            env={**os.environ, "NEXT_DIST_DIR": ".next-scorecard"},
        )
    )

    if not args.skip_smoke:
        smoke_command = [
            str(python_bin),
            "scripts/run_webui_smoke.py",
            "--frontend-url",
            args.frontend_url,
            "--gateway-url",
            args.gateway_url,
            "--timeout-seconds",
            str(args.timeout_seconds),
        ]
        if args.mock:
            smoke_command.append("--mock")
        steps.append(
            _run_step(
                name="webui smoke",
                command=smoke_command,
                cwd=backend_root,
            )
        )

    failed = [step for step in steps if step.returncode != 0]
    summary = {
        "ok": not failed,
        "total_steps": len(steps),
        "failed_steps": [step.name for step in failed],
        "steps": [asdict(step) for step in steps],
    }
    print(summary)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
