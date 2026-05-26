#!/usr/bin/env bash
# Repository-scoped OctoAgent cleanup. Host-wide package, journal, and /var/log
# cleanup belongs to host maintenance, not the OctoAgent project launcher.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting OctoAgent repository cleanup at $(date -Is)"

find "$REPO_ROOT" -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name .mypy_cache \) \
	-prune -exec rm -rf {} + 2>/dev/null || true
find "$REPO_ROOT" -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.tmp" -o -name "*.bak" \) \
	-delete 2>/dev/null || true
find "$REPO_ROOT/tmp" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true

mkdir -p "$REPO_ROOT/tmp" "$REPO_ROOT/runtime/logs"

echo "Cleanup completed at $(date -Is)"
