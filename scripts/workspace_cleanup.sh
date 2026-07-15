#!/usr/bin/env bash
# Compatibility entrypoint for the canonical artifact-governance policy.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT}/backend/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python3"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"
export OCTOAGENT_APP_ROOT="$ROOT"
exec "$PYTHON" -c 'import json; from src.harness.artifact_governance import cleanup_artifacts; print(json.dumps(cleanup_artifacts(dry_run=False), ensure_ascii=False, indent=2))'
