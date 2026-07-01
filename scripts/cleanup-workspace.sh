#!/usr/bin/env bash
# Remove stale empty / oversized agent-generated workspace artifacts.
# Safe to run while services are stopped.
set -euo pipefail
trap 'echo "ERROR: $0 failed at line $LINENO" >> /var/log/octoagent_errors.log; exit 1' ERR


ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WS="${ROOT}/workspace/default/code"

if [ ! -d "$WS" ]; then
    echo "No workspace/default/code dir; nothing to do."
    exit 0
fi

# 1) Remove empty per-thread code dirs (only contain `workspace/` with size <= 16K)
removed=0
for d in "$WS"/*/; do
    [ -d "$d" ] || continue
    sz=$(du -sb "$d" 2>/dev/null | awk '{print $1}')
    if [ -n "$sz" ] && [ "$sz" -lt 65536 ]; then
        rm -rf "$d"
        removed=$((removed+1))
    fi
done
echo "Removed $removed empty per-thread workspace dirs."

# 2) Remove vendored heavy clones (llama.cpp checkouts) — agent re-clones on demand
find "$WS" -maxdepth 4 -type d -name 'llama.cpp' -exec du -sh {} + 2>/dev/null | head
find "$WS" -maxdepth 4 -type d -name 'llama.cpp' -exec rm -rf {} + 2>/dev/null || true

echo "Cleanup complete."