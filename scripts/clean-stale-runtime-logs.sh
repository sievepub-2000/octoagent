#!/usr/bin/env bash
#
# Truncate local runtime logs so current verification scans are not polluted by
# stale errors from previous development runs.

set -euo pipefail
trap 'echo "ERROR: $0 failed at line $LINENO" >> /var/log/octoagent_errors.log; exit 1' ERR


REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

mkdir -p logs

shopt -s nullglob
for log_file in logs/*.log; do
    : > "$log_file"
done

echo "✓ Stale runtime logs truncated"
