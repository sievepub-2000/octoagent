"""Build a release readiness evidence report for OctoAgent.

The project no longer keeps source-level regression tests in the repository, so
this gate turns the remaining production-readiness work into auditable evidence:
compile/lint/build/smoke gate availability, doctor contracts, soak artifacts,
run-record observability, operator governance, and release documentation.
"""

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
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass
class Evidence:
    id: str
    ok: bool
    detail: str
    path: str | None = None
    status: str = "ok"


@dataclass
class ModuleReadiness:
    id: str
    module: str
    score: int
    target_score: int = 95
    evidence: list[Evidence] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)


def _exists(relative_path: str) -> bool:
    return (REPO_ROOT / relative_path).exists()


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_manifest(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return {}
    return payload


def _manifest_evidence(manifest: dict[str, Any], key: str, missing_detail: str) -> Evidence:
    raw = manifest.get(key)
    if not isinstance(raw, dict):
        return Evidence(id=f"manifest.{key}", ok=False, status="missing", detail=missing_detail)
    ok = bool(raw.get("ok"))
    artifact = raw.get("artifact") or raw.get("path")
    detail = str(raw.get("detail") or ("external evidence accepted" if ok else "external evidence reported failure"))
    return Evidence(
        id=f"manifest.{key}",
        ok=ok,
        status="ok" if ok else "fail",
        detail=detail,
        path=str(artifact) if artifact else None,
    )


def _file_mtime_iso(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def _git_status_short() -> str:
    try:
        return subprocess.check_output(["git", "status", "--short"], cwd=REPO_ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostic boundary
        return f"git_status_error={exc}"


def _run_doctor() -> dict[str, Any]:
    from scripts.run_system_doctor import _contract_checks

    checks = _contract_checks(include_git=False)
    return {
        "ok": all(check.status == "ok" for check in checks),
        "checks": [asdict(check) for check in checks],
    }


def _doctor_evidence(doctor: dict[str, Any] | None, check_id: str, manifest: dict[str, Any]) -> Evidence:
    if not doctor:
        manifest_item = _manifest_evidence(
            manifest,
            "live_doctor_contracts",
            "doctor was not executed; run with --run-doctor for live API evidence",
        )
        if manifest_item.ok:
            return Evidence(
                id=f"doctor.{check_id}",
                ok=True,
                status="ok",
                detail=f"covered by external doctor contract bundle: {manifest_item.detail}",
                path=manifest_item.path,
            )
        return Evidence(
            id=f"doctor.{check_id}",
            ok=False,
            status="skipped",
            detail="doctor was not executed; run with --run-doctor for live API evidence",
        )
    for check in doctor.get("checks", []):
        if check.get("id") == check_id:
            return Evidence(
                id=f"doctor.{check_id}",
                ok=check.get("status") == "ok",
                status=str(check.get("status") or "unknown"),
                detail=str(check.get("detail") or check.get("error") or ""),
            )
    return Evidence(id=f"doctor.{check_id}", ok=False, status="missing", detail="doctor check not found")


def _chat_trend_evidence(manifest: dict[str, Any]) -> Evidence:
    summary_path = BACKEND_ROOT / "reports" / "chat-regression-trends-summary.json"
    summary = _read_json(summary_path)
    if isinstance(summary, dict):
        return Evidence(
            id="chat_regression_trend",
            ok=bool(summary.get("ok")),
            status="ok" if summary.get("ok") else "fail",
            detail=(f"records={summary.get('record_count')}, max_render_ms={summary.get('max_render_ms')}, breaches={len(summary.get('threshold_breaches') or [])}"),
            path=str(summary_path.relative_to(REPO_ROOT)),
        )
    manifest_item = _manifest_evidence(
        manifest,
        "chat_regression_trend",
        "no chat regression trend summary found; run make smoke-chat-regression and make chat-regression-report",
    )
    if manifest_item.ok:
        manifest_item.id = "chat_regression_trend"
        return manifest_item
    jsonl_path = BACKEND_ROOT / "reports" / "chat-regression-trends.jsonl"
    return Evidence(
        id="chat_regression_trend",
        ok=False,
        status="missing",
        detail="no chat regression trend summary found; run make smoke-chat-regression and make chat-regression-report",
        path=str(jsonl_path.relative_to(REPO_ROOT)),
    )


def _soak_monitor_evidence(manifest: dict[str, Any]) -> Evidence:
    monitor_path = REPO_ROOT / "workspace" / "runtime" / "soak_reports" / "soak-monitor.json"
    monitor = _read_json(monitor_path)
    if isinstance(monitor, dict):
        ok = bool(monitor.get("ok"))
        complete = bool(monitor.get("complete"))
        return Evidence(
            id="long_soak_monitor",
            ok=ok and complete,
            status="ok" if ok and complete else "pending",
            detail=(f"complete={complete}, ok={ok}, running={monitor.get('running_count')}, failed={monitor.get('failed_count')}, checked_at={monitor.get('checked_at')}"),
            path=str(monitor_path.relative_to(REPO_ROOT)),
        )
    manifest_item = _manifest_evidence(
        manifest,
        "long_soak_monitor",
        "no 2h/8h/24h soak monitor artifact found in workspace/runtime/soak_reports",
    )
    if manifest_item.ok:
        manifest_item.id = "long_soak_monitor"
        return manifest_item
    return Evidence(
        id="long_soak_monitor",
        ok=False,
        status="missing",
        detail="no 2h/8h/24h soak monitor artifact found in workspace/runtime/soak_reports",
        path=str(monitor_path.relative_to(REPO_ROOT)),
    )


def _run_records_evidence(manifest: dict[str, Any]) -> Evidence:
    path = REPO_ROOT / "workspace" / "runtime" / "run_records.jsonl"
    if not path.exists():
        manifest_item = _manifest_evidence(
            manifest,
            "run_record_audit_page",
            "run_records.jsonl has not been created by a real runtime session yet",
        )
        if manifest_item.ok:
            manifest_item.id = "runtime_run_records"
            return manifest_item
        return Evidence(
            id="runtime_run_records",
            ok=False,
            status="missing",
            detail="run_records.jsonl has not been created by a real runtime session yet",
            path=str(path.relative_to(REPO_ROOT)),
        )
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return Evidence(
        id="runtime_run_records",
        ok=bool(lines),
        status="ok" if lines else "empty",
        detail=f"records={len(lines)}, updated_at={_file_mtime_iso(path)}",
        path=str(path.relative_to(REPO_ROOT)),
    )


def _path_evidence(evidence_id: str, relative_path: str, detail: str) -> Evidence:
    ok = _exists(relative_path)
    return Evidence(
        id=evidence_id,
        ok=ok,
        status="ok" if ok else "missing",
        detail=detail if ok else f"missing {relative_path}",
        path=relative_path,
    )


def _env_secret_evidence(env_name: str, detail: str) -> Evidence:
    configured = bool(os.getenv(env_name, "").strip())
    return Evidence(
        id=f"env.{env_name}",
        ok=configured,
        status="configured" if configured else "unset",
        detail=detail if configured else f"{env_name} is unset in this shell",
    )


def _score(base: int, evidence: list[Evidence], blockers: list[str]) -> int:
    ok_count = sum(1 for item in evidence if item.ok)
    missing_count = sum(1 for item in evidence if not item.ok)
    score = base + ok_count * 2 - missing_count * 2 - len(blockers)
    return max(0, min(98, score))


def _module(
    *,
    module_id: str,
    module: str,
    base: int,
    evidence: list[Evidence],
    blockers: list[str],
    next_actions: list[str],
) -> ModuleReadiness:
    score = _score(base, evidence, blockers)
    if not blockers and all(item.ok or item.id.startswith("env.") for item in evidence):
        score = max(score, 95)
    return ModuleReadiness(
        id=module_id,
        module=module,
        score=score,
        evidence=evidence,
        blockers=blockers,
        next_actions=next_actions,
    )


def _evidence_ok(evidence: Evidence) -> bool:
    return evidence.ok


def build_report(*, run_doctor: bool, evidence_manifest: Path | None = None) -> dict[str, Any]:
    manifest = _read_manifest(evidence_manifest)
    doctor = _run_doctor() if run_doctor else None
    chat_trend = _chat_trend_evidence(manifest)
    soak_monitor = _soak_monitor_evidence(manifest)
    run_records = _run_records_evidence(manifest)
    staging_chat = _manifest_evidence(
        manifest,
        "staging_real_conversation",
        "staging real conversation proof is still external",
    )
    operator_auth = _manifest_evidence(
        manifest,
        "operator_auth_binding",
        "operator identity must be bound to real auth claims before production",
    )
    signed_audit = _manifest_evidence(
        manifest,
        "signed_audit_export",
        "audit exports are only non-repudiable when signed audit evidence is present",
    )
    rollback_drill = _manifest_evidence(
        manifest,
        "rollback_drill",
        "production role mapping and rollback drills still require staging execution",
    )
    long_replay = _manifest_evidence(
        manifest,
        "long_conversation_replay",
        "long conversation replay needs fresh staging artifacts",
    )
    mobile_a11y = _manifest_evidence(
        manifest,
        "mobile_accessibility",
        "mobile and accessibility polish still need current screenshot evidence",
    )
    external_retention = _manifest_evidence(
        manifest,
        "external_retention",
        "external run-record retention evidence is missing",
    )
    secrets_rotation = _manifest_evidence(
        manifest,
        "secrets_rotation",
        "secrets rotation evidence is missing",
    )
    regression_bundle = _manifest_evidence(
        manifest,
        "regression_gate_bundle",
        "compile/lint/build/smoke/soak regression evidence bundle is missing",
    )

    modules = [
        _module(
            module_id="core_runtime",
            module="核心对话/多 Agent runtime",
            base=88,
            evidence=[
                _doctor_evidence(doctor, "health-api", manifest),
                _doctor_evidence(doctor, "runtime-long-running-health-api", manifest),
                staging_chat,
                chat_trend,
                soak_monitor,
            ],
            blockers=([] if _evidence_ok(staging_chat) and _evidence_ok(soak_monitor) else ["staging real conversation proof is still external"]),
            next_actions=[
                "Run real staging chat smoke against the external staging URL.",
                "Keep long continuation sessions under soak monitor until all profiles complete.",
            ],
        ),
        _module(
            module_id="runtime_governance",
            module="Runtime 治理/审计",
            base=82,
            evidence=[
                _path_evidence("operator_governance_helpers", "backend/src/governance/operator/__init__.py", "shared operator role, token, confirmation, redaction, and signed audit helpers exist"),
                _path_evidence(
                    "module_lifecycle_smoke",
                    "scripts/verify-module-lifecycles.py",
                    "live module lifecycle closure smoke exists",
                ),
                _doctor_evidence(doctor, "capability-policy-export-api", manifest),
                _env_secret_evidence("OCTO_OPERATOR_TOKEN", "operator token is configured in this shell"),
                _env_secret_evidence("OCTO_OPERATOR_AUDIT_SECRET", "operator audit HMAC secret is configured in this shell"),
                operator_auth,
                signed_audit,
            ],
            blockers=[
                blocker
                for blocker, ok in [
                    ("operator identity must be bound to real auth claims before production", operator_auth.ok),
                    ("audit exports are only non-repudiable when signed audit evidence is present", signed_audit.ok),
                ]
                if not ok
            ],
            next_actions=[
                "Map authenticated user/session claims into operator actor and role headers.",
                "Require HMAC-signed exports in staging and production release gates.",
            ],
        ),
        _module(
            module_id="system_operations",
            module="系统操作能力",
            base=80,
            evidence=[
                _path_evidence("system_executor_boundary", "backend/src/system_executor/app.py", "single authenticated root executor boundary exists"),
                _path_evidence("system_executor_security_tests", "backend/tests/system_executor/test_app.py", "root executor authentication and proxy boundary tests exist"),
                _path_evidence("release_precheck", "backend/scripts/run_release_precheck.py", "release precheck script exists"),
                _path_evidence("docker_distribution", "compose.yaml", "Docker distribution defines the isolated root executor"),
                _path_evidence("docker_installer", "scripts/install-docker.sh", "one-click installer provisions the executor secret and service"),
                rollback_drill,
            ],
            blockers=[] if rollback_drill.ok else ["production role mapping and rollback drills still require staging execution"],
            next_actions=[
                "Keep permission filtering in Harness and root execution behind the authenticated executor.",
                "Run the Docker rollback drill and archive the result.",
            ],
        ),
        _module(
            module_id="memory_context",
            module="记忆/长上下文",
            base=84,
            evidence=[
                _doctor_evidence(doctor, "memory-api", manifest),
                _path_evidence("harness_memory", "backend/src/harness/memory.py", "Markdown source and pgvector recall implementation exists"),
                _path_evidence("memory_governance_doc", "project_docs/backend/SYSTEM_MEMORY_GOVERNANCE.md", "memory governance documentation exists"),
                long_replay,
            ],
            blockers=[] if long_replay.ok else ["long conversation replay needs fresh staging artifacts"],
            next_actions=[
                "Replay 500+ message sessions with tenant continuity and memory retention assertions.",
                "Publish memory quality and retention thresholds in release evidence.",
            ],
        ),
        _module(
            module_id="frontend_workspace",
            module="前端工作台 UX",
            base=85,
            evidence=[
                _path_evidence("frontend_lint_script", "frontend/package.json", "frontend package scripts include lint/typecheck/build gates"),
                _path_evidence("webui_smoke", "backend/scripts/run_webui_smoke.py", "WebUI smoke script exists"),
                _path_evidence("chat_regression_e2e", "backend/scripts/run_chat_regression_e2e.py", "real browser chat regression script exists"),
                chat_trend,
                mobile_a11y,
            ],
            blockers=[] if mobile_a11y.ok and chat_trend.ok else ["mobile and accessibility polish still need current screenshot evidence"],
            next_actions=[
                "Run desktop/mobile right-panel screenshots after any UX change.",
                "Add accessibility checks to the browser smoke lane if source tests remain deleted.",
            ],
        ),
        _module(
            module_id="observability",
            module="可观测性",
            base=78,
            evidence=[
                _doctor_evidence(doctor, "runtime-doctor-api", manifest),
                _doctor_evidence(doctor, "runtime-long-running-health-api", manifest),
                _path_evidence("run_records_endpoint", "backend/src/gateway/routers/runtime.py", "runtime router exposes run records and health endpoints"),
                run_records,
                soak_monitor,
                external_retention,
            ],
            blockers=[] if run_records.ok and external_retention.ok else ["run record independent audit page and external retention are not proven locally"],
            next_actions=[
                "Promote run-record export to a standalone operator audit page.",
                "Ship retention to external storage and add alert thresholds to release readiness.",
            ],
        ),
        _module(
            module_id="deployment_release",
            module="部署/发布",
            base=83,
            evidence=[
                _path_evidence("release_precheck", "backend/scripts/run_release_precheck.py", "release precheck script exists"),
                _path_evidence("release_materials", "project_docs/docs/RELEASE_PACKAGING_AND_MATERIALS.md", "release packaging document exists"),
                _path_evidence("docker_installer", "scripts/install-docker.sh", "single Docker installation path exists"),
                _path_evidence("logrotate", "deploy/system/logrotate.d/octoagent", "logrotate material exists"),
                soak_monitor,
                secrets_rotation,
            ],
            blockers=[] if soak_monitor.ok and secrets_rotation.ok else ["secrets rotation and nightly soak evidence are not fresh in this workspace"],
            next_actions=[
                "Run staging checklist with real service URLs and archive outputs.",
                "Rotate operator/worker/audit secrets before production promotion.",
            ],
        ),
        _module(
            module_id="regression_safety",
            module="回归安全",
            base=45,
            evidence=[
                _path_evidence("backend_compile_gate", "backend/scripts/run_release_precheck.py", "release precheck includes backend compileall and ruff"),
                _path_evidence("frontend_build_gate", "frontend/package.json", "frontend lint/typecheck/build scripts exist"),
                _path_evidence("system_doctor_gate", "backend/scripts/run_system_doctor.py", "system doctor/API contract smoke exists"),
                _path_evidence("system_executor_security_gate", "backend/tests/system_executor/test_app.py", "root executor auth boundary is regression tested"),
                _path_evidence("module_lifecycle_gate", "scripts/verify-module-lifecycles.py", "live module lifecycle smoke exists"),
                _path_evidence("bounded_soak_gate", "backend/scripts/run_long_running_soak.py", "bounded soak smoke exists"),
                _path_evidence("source_test_deletion_policy", "project_docs/CONTRIBUTING.md", "source-test deletion policy is documented"),
                regression_bundle,
            ],
            blockers=[] if regression_bundle.ok else ["source tests are intentionally absent; release confidence must come from gates and soak evidence"],
            next_actions=[
                "Keep compile/lint/build/doctor/smoke/soak as hard release evidence.",
                "Add any new regression as a smoke/contract script rather than deleted source-test trees.",
            ],
        ),
    ]

    module_payloads = [asdict(item) for item in modules]
    overall = round(sum(item.score for item in modules) / len(modules), 1)
    blockers = [f"{item.module}: {blocker}" for item in modules for blocker in item.blockers]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "repo_root": str(REPO_ROOT),
        "ok": overall >= 95 and not blockers,
        "overall_score": overall,
        "target_score": 95,
        "git_status_short": _git_status_short(),
        "doctor_executed": run_doctor,
        "evidence_manifest_path": str(evidence_manifest) if evidence_manifest else None,
        "external_evidence_loaded": bool(manifest),
        "external_evidence_keys": sorted(manifest.keys()),
        "modules": module_payloads,
        "blockers": blockers,
        "minimum_actions_for_95": [
            "Run and archive staging real conversation smoke.",
            "Complete and archive 2h/8h/24h soak monitor with ok=true.",
            "Run release readiness with OCTO_OPERATOR_TOKEN and OCTO_OPERATOR_AUDIT_SECRET configured.",
            "Archive mobile/accessibility screenshots and chat regression trend summary.",
            "Bind operator identity to real auth claims and export signed audit evidence.",
        ],
    }
    return report


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [f"| {item['module']} | {item['score']} | {item['target_score']} | {len(item['blockers'])} |" for item in report["modules"]]
    blockers = "\n".join(f"- {item}" for item in report["blockers"]) or "- None"
    actions = "\n".join(f"- {item}" for item in report["minimum_actions_for_95"])
    evidence_lines: list[str] = []
    for item in report["modules"]:
        evidence_lines.append(f"### {item['module']}")
        for evidence in item["evidence"]:
            marker = "OK" if evidence["ok"] else evidence["status"].upper()
            path_text = f" (`{evidence['path']}`)" if evidence.get("path") else ""
            evidence_lines.append(f"- **{marker}** {evidence['id']}: {evidence['detail']}{path_text}")
        if item["next_actions"]:
            evidence_lines.append("Next actions:")
            evidence_lines.extend(f"- {action}" for action in item["next_actions"])
        evidence_lines.append("")

    content = f"""# OctoAgent Release Readiness Report

Generated at: {report["generated_at"]}

Overall score: **{report["overall_score"]} / {report["target_score"]}**

Release-ready: **{report["ok"]}**

Doctor executed: **{report["doctor_executed"]}**

Git status short:

```text
{report["git_status_short"] or "clean"}
```

| Module | Score | Target | Blockers |
| --- | ---: | ---: | ---: |
{chr(10).join(rows)}

## Blockers

{blockers}

## Minimum Actions For 95+

{actions}

## Evidence

{chr(10).join(evidence_lines)}
"""
    path.write_text(content, encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--run-doctor", action="store_true", help="Run TestClient-backed system doctor checks.")
    parser.add_argument("--evidence-manifest", type=Path, help="Optional JSON manifest containing external staging/soak/audit evidence.")
    parser.add_argument("--min-score", type=float, default=0.0, help="Return non-zero when score is below this threshold.")
    parser.add_argument(
        "--report-dir",
        default=str(REPO_ROOT / "workspace" / "runtime" / "release_readiness"),
        help="Directory for generated JSON and Markdown reports.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = build_report(run_doctor=args.run_doctor, evidence_manifest=args.evidence_manifest)
    report_dir = Path(args.report_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "release-readiness.json"
    markdown_path = report_dir / "release-readiness.md"
    report["report_path"] = str(markdown_path)
    report["json_report_path"] = str(json_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(markdown_path, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Release readiness score: {report['overall_score']} / {report['target_score']}")
        print(f"Release-ready: {report['ok']}")
        print(f"Report: {markdown_path}")
    return 0 if float(report["overall_score"]) >= args.min_score else 1


if __name__ == "__main__":
    raise SystemExit(main())
