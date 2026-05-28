#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_PY="$REPO_ROOT/backend/.venv/bin/python"
TOOLS_DIR="$REPO_ROOT/runtime/tools"
case "${1:-help}" in
  semgrep)
    "$BACKEND_PY" -m pip uninstall -y semgrep || true
    ;;
  trivy)
    rm -f "$TOOLS_DIR/bin/trivy"
    rm -rf "$TOOLS_DIR"/trivy-*
    ;;
  security-cli-venv)
    rm -rf "$REPO_ROOT/runtime/system_tools/security-cli/.venv"
    rmdir --ignore-fail-on-non-empty "$REPO_ROOT/runtime/system_tools/security-cli" 2>/dev/null || true
    ;;
  *) echo "Usage: $0 [semgrep|trivy|security-cli-venv]" >&2; exit 2 ;;
esac
