"""Run and retain soak baselines with threshold checks for release governance."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
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
    from src.runtime.config.paths import get_paths

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


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def build_monitor_status(manifest: dict[str, Any], *, now_epoch: float | None = None) -> dict[str, Any]:
    now_epoch = now_epoch or datetime.now(UTC).timestamp()
    profiles: list[dict[str, Any]] = []
    for item in manifest.get("profiles", []):
        report_path = Path(str(item.get("report_path") or ""))
        log_path = Path(str(item.get("log_path") or ""))
        pid = int(item.get("pid") or 0)
        report_payload: dict[str, Any] = {}
        if report_path.exists():
            try:
                report_payload = json.loads(report_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                report_payload = {"ok": False, "error": "invalid_report_json"}
        if report_payload:
            state = "completed" if bool(report_payload.get("ok")) else "failed"
        elif _pid_running(pid):
            state = "running"
        else:
            state = "missing"
        profiles.append(
            {
                "profile": item.get("profile"),
                "state": state,
                "pid": pid,
                "duration_seconds": item.get("duration_seconds"),
                "report_path": str(report_path),
                "log_path": str(log_path),
                "started_at": item.get("started_at"),
                "checked_at_epoch": round(now_epoch, 3),
                "report": report_payload,
            }
        )
    return {
        "checked_at": datetime.fromtimestamp(now_epoch, UTC).isoformat(),
        "complete": bool(profiles) and all(item["state"] in {"completed", "failed", "missing"} for item in profiles),
        "ok": bool(profiles) and all(item["state"] == "completed" for item in profiles),
        "running_count": sum(1 for item in profiles if item["state"] == "running"),
        "failed_count": sum(1 for item in profiles if item["state"] in {"failed", "missing"}),
        "profiles": profiles,
    }


def write_monitor_report(path: Path, status: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [f"| {item.get('profile')} | {item.get('state')} | {item.get('pid')} | {item.get('duration_seconds')} | `{item.get('report_path')}` |" for item in status.get("profiles", [])]
    content = f"""# Long Soak Monitor

Checked at: {status.get("checked_at")}

Complete: **{status.get("complete")}**

Overall OK: **{status.get("ok")}**

Running profiles: **{status.get("running_count", 0)}**

Failed profiles: **{status.get("failed_count", 0)}**

| Profile | State | PID | Duration seconds | Report |
| --- | --- | ---: | ---: | --- |
{chr(10).join(rows)}
"""
    path.write_text(content, encoding="utf-8")


def start_monitor_background(manifest_path: Path, *, interval_seconds: int) -> dict[str, Any]:
    monitor_output = manifest_path.with_name("soak-monitor.md")
    monitor_json_output = manifest_path.with_name("soak-monitor.json")
    monitor_log = manifest_path.with_name("soak-monitor-loop.log")
    command = [
        sys.executable,
        str(BACKEND_ROOT / "scripts" / "run_soak_baseline_suite.py"),
        "--monitor-manifest",
        str(manifest_path),
        "--monitor-output",
        str(monitor_output),
        "--monitor-json-output",
        str(monitor_json_output),
        "--monitor-loop",
        "--monitor-interval-seconds",
        str(max(1, interval_seconds)),
        "--json",
    ]
    log_fh = monitor_log.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=BACKEND_ROOT,
        env={**os.environ, "PYTHONPATH": str(BACKEND_ROOT)},
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return {
        "pid": process.pid,
        "monitor_report_path": str(monitor_output),
        "monitor_json_path": str(monitor_json_output),
        "monitor_log_path": str(monitor_log),
        "interval_seconds": max(1, interval_seconds),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", default="2h,8h,24h", help="Comma-separated profiles: 2h,8h,24h or raw seconds.")
    parser.add_argument("--report-dir", default="")
    parser.add_argument("--sample-interval-seconds", type=int, default=300)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--background", action="store_true", help="Start profiles as detached background jobs and return immediately.")
    parser.add_argument("--start-monitor", action="store_true", help="When starting background profiles, also start the monitor loop in the background.")
    parser.add_argument("--monitor-manifest", default="", help="Existing suite JSON to inspect without starting new jobs.")
    parser.add_argument("--monitor-output", default="")
    parser.add_argument("--monitor-json-output", default="")
    parser.add_argument("--monitor-loop", action="store_true", help="Poll the monitor manifest until all profiles finish.")
    parser.add_argument("--monitor-interval-seconds", type=int, default=600)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report_dir = Path(args.report_dir).expanduser() if args.report_dir else _default_report_dir()
    report_dir.mkdir(parents=True, exist_ok=True)
    if args.monitor_manifest:
        manifest_path = Path(args.monitor_manifest).expanduser()
        output = Path(args.monitor_output).expanduser() if args.monitor_output else manifest_path.with_name("soak-monitor.md")
        json_output = Path(args.monitor_json_output).expanduser() if args.monitor_json_output else output.with_suffix(".json")
        if args.start_monitor:
            monitor_process = start_monitor_background(manifest_path, interval_seconds=args.monitor_interval_seconds)
            print(json.dumps({"ok": True, "monitor_process": monitor_process}, ensure_ascii=False, indent=2 if args.json else None))
            return 0
        while True:
            status = build_monitor_status(json.loads(manifest_path.read_text(encoding="utf-8")))
            write_monitor_report(output, status)
            json_output.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
            if not args.monitor_loop or status.get("complete"):
                break
            time.sleep(max(1, args.monitor_interval_seconds))
        print(json.dumps(status | {"monitor_report_path": str(output), "monitor_json_path": str(json_output)}, ensure_ascii=False, indent=2 if args.json else None))
        return 1 if int(status.get("failed_count") or 0) else 0

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
    monitor_status = build_monitor_status(payload)
    monitor_path = report_dir / "soak-monitor.md"
    write_monitor_report(monitor_path, monitor_status)
    monitor_process = start_monitor_background(suite_path, interval_seconds=args.sample_interval_seconds) if args.background and args.start_monitor else {}
    print(json.dumps(payload | {"suite_report_path": str(suite_path), "monitor_report_path": str(monitor_path), "monitor_process": monitor_process}, ensure_ascii=False, indent=2 if args.json else None))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
