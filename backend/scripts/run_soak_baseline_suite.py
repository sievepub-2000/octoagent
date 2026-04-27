"""Run and retain soak baselines with threshold checks for release governance."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass
class SoakBaselineSuiteReport:
    ok: bool = True
    report_dir: str = ""
    profiles: list[dict[str, Any]] = field(default_factory=list)


def _default_report_dir() -> Path:
    from src.config.paths import get_paths

    return get_paths().runtime_root / "soak_reports"


def _profile_seconds(profile: str) -> int:
    if profile == "2h":
        return 2 * 60 * 60
    if profile == "8h":
        return 8 * 60 * 60
    if profile == "24h":
        return 24 * 60 * 60
    return max(1, int(profile))


def run_profile(profile: str, *, report_dir: Path, sample_interval_seconds: int, iterations: int) -> dict[str, Any]:
    duration = _profile_seconds(profile)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / f"soak-{profile}-{timestamp}.json"
    command = [
        sys.executable,
        str(BACKEND_ROOT / "scripts" / "run_long_running_soak.py"),
        "--iterations",
        str(iterations),
        "--duration-seconds",
        str(duration),
        "--sample-interval-seconds",
        str(sample_interval_seconds),
        "--report-path",
        str(report_path),
    ]
    completed = subprocess.run(command, cwd=BACKEND_ROOT, check=False, text=True, capture_output=True)
    payload: dict[str, Any] = {}
    if report_path.exists():
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "profile": profile,
        "duration_seconds": duration,
        "report_path": str(report_path),
        "returncode": completed.returncode,
        "ok": completed.returncode == 0 and bool(payload.get("ok", False)),
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
        "report": payload,
    }


def start_profile_background(profile: str, *, report_dir: Path, sample_interval_seconds: int, iterations: int) -> dict[str, Any]:
    duration = _profile_seconds(profile)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / f"soak-{profile}-{timestamp}.json"
    log_path = report_dir / f"soak-{profile}-{timestamp}.log"
    command = [
        sys.executable,
        str(BACKEND_ROOT / "scripts" / "run_long_running_soak.py"),
        "--iterations",
        str(iterations),
        "--duration-seconds",
        str(duration),
        "--sample-interval-seconds",
        str(sample_interval_seconds),
        "--report-path",
        str(report_path),
    ]
    log_fh = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=BACKEND_ROOT,
        env={**os.environ, "PYTHONPATH": str(BACKEND_ROOT)},
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return {
        "profile": profile,
        "duration_seconds": duration,
        "pid": process.pid,
        "report_path": str(report_path),
        "log_path": str(log_path),
        "started_at": datetime.now(UTC).isoformat(),
        "ok": True,
        "background": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", default="2h,8h,24h", help="Comma-separated profiles: 2h,8h,24h or raw seconds.")
    parser.add_argument("--report-dir", default="")
    parser.add_argument("--sample-interval-seconds", type=int, default=300)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--background", action="store_true", help="Start profiles as detached background jobs and return immediately.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report_dir = Path(args.report_dir).expanduser() if args.report_dir else _default_report_dir()
    report_dir.mkdir(parents=True, exist_ok=True)
    report = SoakBaselineSuiteReport(report_dir=str(report_dir))
    for profile in [item.strip() for item in args.profiles.split(",") if item.strip()]:
        kwargs = {
            "report_dir": report_dir,
            "sample_interval_seconds": max(1, args.sample_interval_seconds),
            "iterations": max(1, min(args.iterations, 500)),
        }
        result = start_profile_background(profile, **kwargs) if args.background else run_profile(profile, **kwargs)
        report.profiles.append(result)
        report.ok = report.ok and bool(result.get("ok"))

    payload = asdict(report)
    suite_path = report_dir / f"soak-suite-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    suite_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload | {"suite_report_path": str(suite_path)}, ensure_ascii=False, indent=2 if args.json else None))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
