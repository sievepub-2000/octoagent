#!/bin/bash
# LangGraph contract pruning - runs daily at 4 AM
# Only logs audit events when actual pruning occurs (fixed in workflow_contract.py)

set -e

LOG_FILE="/home/sieve-pub/public-workspace/octoagent/logs/langgraph_prune.log"
REPO_ROOT="/home/sieve-pub/public-workspace/octoagent"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] Starting LangGraph contract pruning..." >> "$LOG_FILE"

if [[ -r "${REPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.env"
  set +a
fi

cd "${REPO_ROOT}"

# Run prune via Python
if [[ -x "${REPO_ROOT}/backend/.venv/bin/python3" ]]; then
  PYTHON_CMD=("${REPO_ROOT}/backend/.venv/bin/python3")
else
  PYTHON_CMD=(docker compose exec -T gateway /app/backend/.venv/bin/python)
fi

"${PYTHON_CMD[@]}" -c "
import sys
sys.path.insert(0, 'backend')
from src.agents.runtime import get_langgraph_workflow_contract_service

contract = get_langgraph_workflow_contract_service()
result = contract.prune(
    max_checkpoints_per_thread=20,
    max_runs_per_thread=100,
)

print(f'Pruning complete: {result}')
" >> "$LOG_FILE" 2>&1

echo "[$TIMESTAMP] Pruning finished." >> "$LOG_FILE"
