"""Contract smoke for the release readiness evidence manifest.

The repository does not keep source test suites, so this script validates the
release-readiness gate contract as an operator smoke check.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.run_release_readiness import build_report  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args()


def main() -> int:
    _parse_args()
    with tempfile.TemporaryDirectory() as tmp_dir:
        manifest_path = Path(tmp_dir) / "evidence.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "staging_real_conversation": {"ok": True, "artifact": "s3://octoagent/staging-chat.json", "detail": "real staging chat passed"},
                    "live_doctor_contracts": {"ok": True, "artifact": "s3://octoagent/system-doctor.json", "detail": "doctor contract bundle passed"},
                    "chat_regression_trend": {"ok": True, "artifact": "s3://octoagent/chat-trends.json", "detail": "chat trend threshold passed"},
                    "long_soak_monitor": {"ok": True, "artifact": "s3://octoagent/soak-monitor.json", "detail": "2h/8h/24h profiles complete"},
                    "operator_auth_binding": {"ok": True, "artifact": "s3://octoagent/auth-binding.json", "detail": "auth claims mapped to operator"},
                    "signed_audit_export": {"ok": True, "artifact": "s3://octoagent/audit-export.json", "detail": "HMAC signed export verified"},
                    "rollback_drill": {"ok": True, "artifact": "s3://octoagent/rollback.md", "detail": "rollback drill completed"},
                    "long_conversation_replay": {"ok": True, "artifact": "s3://octoagent/replay.json", "detail": "520 message replay stable"},
                    "mobile_accessibility": {"ok": True, "artifact": "s3://octoagent/a11y.zip", "detail": "mobile and accessibility checks archived"},
                    "run_record_audit_page": {"ok": True, "artifact": "s3://octoagent/run-records.jsonl", "detail": "run records retained externally"},
                    "external_retention": {"ok": True, "artifact": "s3://octoagent/retention-policy.md", "detail": "external retention verified"},
                    "secrets_rotation": {"ok": True, "artifact": "s3://octoagent/secrets-rotation.md", "detail": "release secrets rotated"},
                    "regression_gate_bundle": {"ok": True, "artifact": "s3://octoagent/regression-gates.json", "detail": "compile/lint/build/smoke/soak bundle archived"},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        report = build_report(run_doctor=False, evidence_manifest=manifest_path)
    if not report["external_evidence_loaded"]:
        raise SystemExit("expected evidence manifest to load")
    if report["overall_score"] < 95:
        raise SystemExit(f"expected manifest-backed score >=95, got {report['overall_score']}")
    if report["blockers"]:
        raise SystemExit(f"expected no manifest-backed blockers, got {report['blockers']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
