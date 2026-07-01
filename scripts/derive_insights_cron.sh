#!/usr/bin/env bash
# derive_insights cron script - runs daily at 5 AM
# Triggers the reflection engine to analyze recent execution data
# and generate improvement insights for skill evolution.

set -euo pipefail
trap 'echo "ERROR: $0 failed at line $LINENO" >> $LOG_FILE; exit 1' ERR


REPO_ROOT="/home/sieve-pub/public-workspace/octoagent"
LOG_FILE="${REPO_ROOT}/logs/derive_insights.log"
VENV="${REPO_ROOT}/backend/.venv/bin/python3"

mkdir -p "${REPO_ROOT}/logs"

echo "=== derive_insights run at $(date -u '+%Y-%m-%dT%H:%M:%SZ') ===" >> "$LOG_FILE"

cd "$REPO_ROOT" || exit 1

# Run derive_insights via the reflection service
"$VENV" -c "
import sys
sys.path.insert(0, 'backend/src')

from pathlib import Path
from src.harness.reflection.service import ReflectionService

store_dir = Path('workspace/runtime/reflection')
store_dir.mkdir(parents=True, exist_ok=True)

service = ReflectionService(store_dir=store_dir)
insights = service.derive_insights()

print(f'Derived {len(insights)} insight(s)', file=sys.stderr)
for ins in insights:
    print(f'  [{ins.category}] {ins.description[:100]}', file=sys.stderr)
    if ins.suggested_action:
        print(f'    -> {ins.suggested_action[:100]}', file=sys.stderr)

if insights:
    # Persist insights
    service._persist()
    print(f'Saved {len(insights)} insight(s) to store', file=sys.stderr)
else:
    print('No new insights derived this run', file=sys.stderr)
" >> "$LOG_FILE" 2>&1

echo "=== derive_insights completed at $(date -u '+%Y-%m-%dT%H:%M:%SZ') ===" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
