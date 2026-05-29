"""Daily OctoAgent self-check, environment repair, safe update, and memory record.

This script intentionally uses only the Python standard library so it can run
from the system Python even when the project virtual environment is broken.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend"
VENV = BACKEND_ROOT / ".venv"
RUNTIME_DIR = REPO_ROOT / "workspace" / "runtime" / "maintenance"
LOG_DIR = REPO_ROOT / "runtime" / "logs"
MEMORY_PATH = REPO_ROOT / "workspace" / "default" / "memory.json"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def today_id() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def find_python() -> str:
    for candidate in ("python3.12", "python3", "python"):
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError("No Python executable found")


def tail(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


class Runner:
    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.steps: list[dict[str, Any]] = []

    def run(
        self,
        step_id: str,
        command: list[str],
        *,
        cwd: Path = REPO_ROOT,
        timeout: int = 900,
        env: dict[str, str] | None = None,
        allow_fail: bool = True,
    ) -> dict[str, Any]:
        started = time.monotonic()
        if self.dry_run:
            result = {
                "id": step_id,
                "status": "skipped",
                "detail": "dry-run",
                "command": command,
                "seconds": 0.0,
            }
            self.steps.append(result)
            return result

        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=proc_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            output = completed.stdout or ""
            status = "ok" if completed.returncode == 0 else "fail"
            result = {
                "id": step_id,
                "status": status,
                "returncode": completed.returncode,
                "command": command,
                "seconds": round(time.monotonic() - started, 3),
                "output_tail": tail(output),
            }
        except subprocess.TimeoutExpired as exc:
            result = {
                "id": step_id,
                "status": "fail",
                "returncode": 124,
                "command": command,
                "seconds": round(time.monotonic() - started, 3),
                "output_tail": tail((exc.stdout or "") if isinstance(exc.stdout, str) else ""),
                "error": f"timeout after {timeout}s",
            }
        self.steps.append(result)
        if result["status"] != "ok" and not allow_fail:
            raise RuntimeError(f"step failed: {step_id}")
        return result


def is_git_dirty() -> bool:
    proc = subprocess.run(["git", "status", "--short"], cwd=REPO_ROOT, text=True, stdout=subprocess.PIPE, check=False)
    return bool(proc.stdout.strip())


def git_update(runner: Runner, *, enabled: bool) -> dict[str, Any]:
    result: dict[str, Any] = {"enabled": enabled, "updated": False, "skipped": False, "reason": None}
    if not enabled:
        result.update({"skipped": True, "reason": "disabled"})
        return result
    if not (REPO_ROOT / ".git").exists():
        result.update({"skipped": True, "reason": "not a git checkout"})
        return result

    runner.run("git-fetch", ["git", "fetch", "origin", "main"], timeout=600)
    if is_git_dirty():
        result.update({"skipped": True, "reason": "working tree has local changes"})
        return result

    counts = runner.run(
        "git-divergence",
        ["git", "rev-list", "--left-right", "--count", "HEAD...origin/main"],
        timeout=60,
    )
    output = (counts.get("output_tail") or "").strip()
    try:
        left, right = [int(part) for part in output.split()[:2]]
    except Exception:
        result.update({"skipped": True, "reason": f"could not parse divergence: {output}"})
        return result
    if left != 0:
        result.update({"skipped": True, "reason": f"local commits ahead/diverged: left={left}, right={right}"})
        return result
    if right == 0:
        result.update({"skipped": True, "reason": "already up to date"})
        return result

    pull = runner.run("git-pull-ff-only", ["git", "pull", "--ff-only", "origin", "main"], timeout=900)
    result["updated"] = pull["status"] == "ok"
    if not result["updated"]:
        result.update({"skipped": True, "reason": "git pull failed"})
    return result


def ensure_single_venv() -> dict[str, Any]:
    venvs: list[str] = []
    prune = {".git", "node_modules", ".next", "runtime", "llm-server", "__pycache__"}
    for root, dirs, files in os.walk(REPO_ROOT):
        root_path = Path(root)
        if root_path == VENV:
            if "pyvenv.cfg" in files:
                venvs.append(str(root_path.relative_to(REPO_ROOT)))
            dirs[:] = []
            continue
        dirs[:] = [name for name in dirs if name not in prune]
        if "pyvenv.cfg" in files:
            venvs.append(str(root_path.relative_to(REPO_ROOT)))
    return {
        "venvs": sorted(venvs),
        "ok": sorted(venvs) == ["backend/.venv"],
    }


def repair_backend_env(runner: Runner) -> dict[str, Any]:
    py = find_python()
    created = False
    if not (VENV / "bin" / "python").exists():
        runner.run("backend-venv-create", [py, "-m", "venv", str(VENV)], timeout=600, allow_fail=False)
        created = True
    venv_python = str(VENV / "bin" / "python")
    runner.run("backend-ensure-pip", [venv_python, "-m", "ensurepip", "--upgrade"], timeout=300)

    critical_import_command = [
        venv_python,
        "-c",
        "import fastapi,pydantic,duckdb,httpx,uvicorn,langgraph,scrapling; print('critical imports ok')",
    ]
    imports = runner.run("backend-critical-imports", critical_import_command, cwd=BACKEND_ROOT, timeout=120)
    if imports["status"] == "ok" and not created:
        return {"created": created, "critical_imports_ok": True, "dependency_sync": "skipped-imports-ok"}

    if shutil.which("uv"):
        sync = runner.run("backend-uv-sync-frozen", ["uv", "sync", "--frozen"], cwd=BACKEND_ROOT, timeout=600)
        if sync["status"] != "ok":
            runner.run("backend-uv-sync", ["uv", "sync"], cwd=BACKEND_ROOT, timeout=600)
    else:
        runner.run(
            "backend-pip-install-requirements",
            [venv_python, "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=BACKEND_ROOT,
            timeout=900,
        )
        runner.run(
            "backend-pip-install-editable",
            [venv_python, "-m", "pip", "install", "-e", "."],
            cwd=BACKEND_ROOT,
            timeout=900,
        )

    imports_after = runner.run("backend-critical-imports-after-repair", critical_import_command, cwd=BACKEND_ROOT, timeout=120)
    return {
        "created": created,
        "critical_imports_ok": imports_after["status"] == "ok",
        "dependency_sync": "attempted-repair",
    }


def repair_frontend_env(runner: Runner) -> dict[str, Any]:
    if not shutil.which("pnpm"):
        return {"ok": False, "reason": "pnpm missing"}
    runner.run(
        "frontend-node-modules-permissions",
        ["sudo", "chown", "-R", "sieve-pub:sieve-pub", "node_modules"],
        cwd=FRONTEND_ROOT,
        timeout=900,
    )
    install = runner.run(
        "frontend-pnpm-install-frozen",
        ["pnpm", "install", "--frozen-lockfile"],
        cwd=FRONTEND_ROOT,
        timeout=1800,
        env={"CI": "true"},
    )
    return {"ok": install["status"] == "ok"}


def _iter_manifest_values(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_manifest_values(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_manifest_values(item)


def frontend_build_ready() -> tuple[bool, list[str]]:
    missing: list[str] = []
    next_root = FRONTEND_ROOT / ".next"
    required_manifest = next_root / "required-server-files.json"
    if not (next_root / "BUILD_ID").exists():
        missing.append(".next/BUILD_ID")
    if not required_manifest.exists():
        missing.append(".next/required-server-files.json")
        return False, missing
    try:
        payload = json.loads(required_manifest.read_text())
        for item in payload.get("files", []):
            if not (FRONTEND_ROOT / item).exists():
                missing.append(item)
    except Exception as exc:
        missing.append(f"required-server-files.json parse error: {exc}")

    for manifest_name in ("build-manifest.json", "app-build-manifest.json", "react-loadable-manifest.json"):
        manifest_path = next_root / manifest_name
        if not manifest_path.exists():
            continue
        try:
            payload = json.loads(manifest_path.read_text())
        except Exception as exc:
            missing.append(f"{manifest_name} parse error: {exc}")
            continue
        for item in _iter_manifest_values(payload):
            relative = None
            if item.startswith("static/"):
                relative = item
            elif item.startswith("/_next/static/"):
                relative = item[len("/_next/") :]
            if relative and not (next_root / relative).exists():
                missing.append(f".next/{relative}")
    return not missing, missing


def repair_frontend_build(runner: Runner) -> dict[str, Any]:
    ready, missing = frontend_build_ready()
    if ready:
        return {"rebuilt": False, "missing": []}
    build = runner.run("frontend-next-build", ["pnpm", "exec", "next", "build"], cwd=FRONTEND_ROOT, timeout=2400)
    ready_after, missing_after = frontend_build_ready()
    return {"rebuilt": True, "build_ok": build["status"] == "ok", "missing_before": missing, "missing_after": missing_after, "ready": ready_after}


def verify_scrapling_fetch(runner: Runner) -> dict[str, Any]:
    venv_python = str(VENV / "bin" / "python")
    code = """
import json
from src.community.scrapling.tools import scrapling_fetch
payload = json.loads(scrapling_fetch.invoke({'url': 'https://example.com'}))
if payload.get('error') or 'content' not in payload:
    raise SystemExit(payload)
print(json.dumps({'ok': True, 'engine': payload.get('engine'), 'title': payload.get('title')}))
""".strip()
    step = runner.run("scrapling-fetch-smoke", [venv_python, "-c", code], cwd=BACKEND_ROOT, timeout=90)
    return {"ok": step["status"] == "ok", "step": step}


def cleanup_runtime_temps(runner: Runner) -> dict[str, Any]:
    script = f"""
set -euo pipefail
repo={str(REPO_ROOT)!r}
active_locks=$(ps -eo args | grep -o 'Xvfb :[0-9][0-9]*' | awk '{{sub(/^:/, "", $2); print ".X" $2 "-lock"}}' | sort -u)
removed_xlocks=0
while IFS= read -r lock; do
  base=$(basename "$lock")
  if printf '%s\n' "$active_locks" | grep -qx "$base"; then
    continue
  fi
  rm -f -- "$lock"
  display=${{base#.X}}; display=${{display%-lock}}
  rm -f -- "/tmp/.X11-unix/X${{display}}" 2>/dev/null || true
  removed_xlocks=$((removed_xlocks + 1))
done < <(find /tmp -maxdepth 1 -name '.X*-lock' -type f -mmin +30 -print 2>/dev/null)
repo_xvfb_before=$(find "$repo/tmp" -maxdepth 1 -type d -name 'xvfb-run.*' 2>/dev/null | wc -l)
find "$repo/tmp" -maxdepth 1 -type d -name 'xvfb-run.*' -mmin +360 -exec rm -rf -- {{}} + 2>/dev/null || true
find /tmp -maxdepth 1 -type d \\( -name 'playwright-artifacts-*' -o -name 'playwright_chromiumdev_profile-*' \\) -mmin +360 -exec rm -rf -- {{}} + 2>/dev/null || true
find /tmp -maxdepth 1 -type f \\( -name 'octoagent-*.html' -o -name 'chunk-*.js' -o -name 'test_write*.txt' -o -name 'tor*.log' \\) -mmin +60 -delete 2>/dev/null || true
repo_xvfb_after=$(find "$repo/tmp" -maxdepth 1 -type d -name 'xvfb-run.*' 2>/dev/null | wc -l)
xlocks_after=$(find /tmp -maxdepth 1 -name '.X*-lock' -type f 2>/dev/null | wc -l)
printf '{{"removed_xlocks":%s,"repo_xvfb_before":%s,"repo_xvfb_after":%s,"xlocks_after":%s}}\n' "$removed_xlocks" "$repo_xvfb_before" "$repo_xvfb_after" "$xlocks_after"
""".strip()
    step = runner.run("runtime-temp-cleanup", ["bash", "-lc", script], timeout=180)
    try:
        payload = json.loads(step.get("output_tail") or "{}")
    except Exception:
        payload = None
    return {"ok": step["status"] == "ok", "payload": payload, "step": step}


def disable_unused_tor(runner: Runner) -> dict[str, Any]:
    if os.environ.get("OCTOAGENT_ENABLE_TOR", "0").strip().lower() in {"1", "true", "yes", "on"}:
        return {"ok": True, "skipped": True, "reason": "OCTOAGENT_ENABLE_TOR is set"}
    script = """
set -euo pipefail
systemctl disable --now tor.service >/dev/null 2>&1 || true
systemctl stop tor@default.service >/dev/null 2>&1 || true
systemctl mask tor@default.service >/dev/null 2>&1 || true
systemctl reset-failed tor.service tor@default.service >/dev/null 2>&1 || true
systemctl daemon-reload >/dev/null 2>&1 || true
printf '{"tor_service":"%s","tor_default":"%s","tor_default_active":"%s"}
'   "$(systemctl is-enabled tor.service 2>/dev/null || true)"   "$(systemctl is-enabled tor@default.service 2>/dev/null || true)"   "$(systemctl is-active tor@default.service 2>/dev/null || true)"
""".strip()
    step = runner.run("disable-unused-tor", ["bash", "-lc", script], timeout=120)
    try:
        payload = json.loads(step.get("output_tail") or "{}")
    except Exception:
        payload = None
    ok = step["status"] == "ok" and payload is not None and payload.get("tor_default_active") != "active"
    return {"ok": ok, "payload": payload, "step": step}


def live_health(runner: Runner) -> dict[str, Any]:
    entry_port = os.environ.get("OCTO_NGINX_PORT", "19800")
    base_url = f"http://127.0.0.1:{entry_port}"
    checks = {
        "models": ["curl", "-fsS", "-m", "10", f"{base_url}/api/models"],
        "workspace": ["curl", "-fsS", "-L", "-m", "15", f"{base_url}/workspace"],
        "qq_identity": ["curl", "-fsS", "-m", "10", f"{base_url}/api/channels/qq/identity"],
    }
    status: dict[str, Any] = {}
    for name, cmd in checks.items():
        step = runner.run(f"live-{name}", cmd, timeout=30)
        output = str(step.get("output_tail") or "")
        ok = step["status"] == "ok" and "__next_error__" not in output
        detail: dict[str, Any] = {}
        if name == "qq_identity" and ok:
            try:
                payload = json.loads(output)
                bridge_ready = bool(payload.get("bridge_ready"))
                qrcode_available = bool((payload.get("qrcode") or {}).get("available"))
                logged_in = bool(payload.get("logged_in"))
                reply_ready = bool(payload.get("reply_ready"))
                detail = {
                    "logged_in": logged_in,
                    "account_id": payload.get("account_id"),
                    "reply_ready": reply_ready,
                    "bridge_ready": bridge_ready,
                    "login_required": bridge_ready and qrcode_available and not logged_in,
                    "error": payload.get("error"),
                }
                ok = (logged_in and reply_ready) or (bridge_ready and qrcode_available)
            except Exception as exc:
                ok = False
                detail = {"parse_error": str(exc)}
        status[name] = {
            "ok": ok,
            "contains_next_error": "__next_error__" in output,
            **detail,
        }
    return status


def restart_if_needed(runner: Runner, live: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    needs_restart = force or not all(item.get("ok") for item in live.values())
    if not needs_restart:
        return {"restarted": False, "reason": "live health ok"}
    step = runner.run("service-restart", ["sudo", "systemctl", "restart", "octoagent-local.service"], timeout=1200)
    runner.run("service-active", ["systemctl", "is-active", "octoagent-local.service"], timeout=60)
    return {"restarted": step["status"] == "ok", "reason": "health failed or forced"}


def wait_for_live_health_after_restart(runner: Runner, *, timeout_seconds: int = 180) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = live_health(runner)
        if all(item.get("ok") for item in latest.values()):
            return latest
        time.sleep(5)
    return latest


def run_doctor(runner: Runner) -> dict[str, Any]:
    venv_python = str(VENV / "bin" / "python")
    step = runner.run(
        "system-doctor",
        [venv_python, "backend/scripts/run_system_doctor.py", "--json", "--skip-git"],
        cwd=REPO_ROOT,
        timeout=900,
    )
    try:
        payload = json.loads(step.get("output_tail") or "{}")
    except Exception:
        payload = None
    return {"ok": step["status"] == "ok", "payload": payload}


def record_memory(report: dict[str, Any]) -> dict[str, Any]:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if MEMORY_PATH.exists():
        data = json.loads(MEMORY_PATH.read_text())
    else:
        data = {"version": "1.0", "facts": [], "history": {}, "user": {}}
    facts = data.setdefault("facts", [])
    report_path = report.get("report_path", "")
    ok = bool(report.get("ok"))
    fact_content = (
        f"OctoAgent daily self-check ran at {report['started_at']} with status={'ok' if ok else 'fail'}; "
        f"git_update={report.get('git_update', {}).get('updated')}; "
        f"git_skip_reason={report.get('git_update', {}).get('reason')}; "
        f"backend_venv_ok={report.get('venv_inventory', {}).get('ok')}; "
        f"frontend_ready={report.get('frontend_build', {}).get('ready', True)}; "
        f"service_restart={report.get('restart', {}).get('restarted')}; report={report_path}"
    )
    digest = hashlib.sha256((report["started_at"] + fact_content).encode("utf-8")).hexdigest()[:10]
    facts.append(
        {
            "id": f"daily_self_check_{digest}",
            "content": fact_content,
            "category": "system_maintenance",
            "confidence": 1.0,
            "createdAt": report["finished_at"],
            "source": "octoagent_daily_self_check",
            "sourceMetadata": {
                "report_path": report_path,
                "ok": ok,
                "schedule": "daily 04:00 local time",
                "memory_pipeline": "system_maintenance_self_review",
            },
        }
    )
    blocks = data.setdefault("memory_blocks", {})
    blocks["daily_self_check"] = {
        "label": "Daily self-check and environment repair",
        "value": fact_content,
        "updatedAt": report["finished_at"],
        "readOnly": False,
        "metadata": {"report_path": report_path, "ok": ok},
    }
    data["lastUpdated"] = report["finished_at"]
    tmp = MEMORY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(MEMORY_PATH)
    return {"memory_path": str(MEMORY_PATH), "fact_id": facts[-1]["id"]}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-update", action="store_true", help="Skip safe git fast-forward update.")
    parser.add_argument("--force-restart", action="store_true", help="Restart OctoAgent after checks.")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; do not execute commands.")
    parser.add_argument("--no-memory", action="store_true", help="Do not append maintenance result to memory.json.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    runner = Runner(dry_run=args.dry_run)
    started = utc_now()
    report_path = RUNTIME_DIR / f"daily-self-check-{today_id()}.json"
    report: dict[str, Any] = {
        "started_at": started,
        "repo_root": str(REPO_ROOT),
        "report_path": str(report_path),
    }
    lock_path = RUNTIME_DIR / "daily-self-check.lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, started.encode("utf-8"))
        os.close(lock_fd)
    except FileExistsError:
        report.update({"ok": False, "error": "daily self-check already running", "finished_at": utc_now(), "steps": []})
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    try:
        report["git_update"] = git_update(runner, enabled=not args.skip_update)
        report["dependency_check"] = runner.run("dependency-check", ["bash", "scripts/check.sh"], timeout=300)
        report["venv_inventory"] = ensure_single_venv()
        report["backend_env"] = repair_backend_env(runner)
        report["venv_inventory_after"] = ensure_single_venv()
        report["frontend_env"] = repair_frontend_env(runner)
        report["frontend_build"] = repair_frontend_build(runner)
        report["scrapling_fetch"] = verify_scrapling_fetch(runner)
        report["runtime_temp_cleanup"] = cleanup_runtime_temps(runner)
        report["tor"] = disable_unused_tor(runner)
        report["doctor"] = run_doctor(runner)
        live = live_health(runner)
        report["live_health"] = live
        report["restart"] = restart_if_needed(runner, live, force=args.force_restart)
        if report["restart"].get("restarted"):
            report["live_health_after_restart"] = wait_for_live_health_after_restart(runner)
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

    report["finished_at"] = utc_now()
    failing_steps = [step for step in runner.steps if step.get("status") == "fail"]
    report["steps"] = runner.steps
    live_final = report.get("live_health_after_restart") or report.get("live_health") or {}
    report["ok"] = (
        not failing_steps
        and report.get("venv_inventory_after", {}).get("ok") is True
        and report.get("scrapling_fetch", {}).get("ok") is True
        and report.get("runtime_temp_cleanup", {}).get("ok") is True
        and report.get("tor", {}).get("ok") is True
        and all(item.get("ok") for item in live_final.values())
    )
    if not args.no_memory:
        try:
            report["memory_record"] = record_memory(report)
        except Exception as exc:
            report["memory_record_error"] = str(exc)
            report["ok"] = False
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"ok": report["ok"], "report_path": str(report_path), "failed_steps": [s["id"] for s in failing_steps]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
