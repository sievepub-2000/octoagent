REPO_ROOT="$REPO_ROOT"

#!/bin/bash
# OctoAgent workspace periodic cleanup — safe to run at any time.
# Never touches workspace/runtime/memory (RAG DB) or runtime/cache (model weights).
set +e
ROOT=$REPO_ROOT
LOG="$ROOT/logs/workspace_cleanup.log"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Cleanup start" >> "$LOG"

# 1. Remove thread output dirs older than 30 days
find "$ROOT/workspace/default/threads" -mindepth 2 -maxdepth 2 \
  -name "outputs" -type d -mtime +30 2>/dev/null | while read -r dir; do
  rm -rf "$dir"
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Removed: $dir" >> "$LOG"
done

# 2. Remove Python pycache (harmless — auto-rebuilt on next import)
find "$ROOT/backend/src" -name "__pycache__" -type d \
  -exec rm -rf {} + 2>/dev/null || true

# 3. Rotate run_records.jsonl when it grows beyond 50 MB
RUNLOG="$ROOT/workspace/runtime/run_records.jsonl"
if [ -f "$RUNLOG" ]; then
  SIZE=$(stat -c%s "$RUNLOG" 2>/dev/null || echo 0)
  if [ "$SIZE" -gt 52428800 ]; then
    mv "$RUNLOG" "${RUNLOG}.prev"
    touch "$RUNLOG"
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] run_records.jsonl rotated (${SIZE}B)" >> "$LOG"
  fi
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Cleanup done" >> "$LOG"
tail -500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
