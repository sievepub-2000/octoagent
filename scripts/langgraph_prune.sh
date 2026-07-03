#!/bin/bash
# LangGraph contract pruning - runs daily at 4 AM
# Only logs audit events when actual pruning occurs (fixed in workflow_contract.py)

set -e

LOG_FILE="/home/sieve-pub/public-workspace/octoagent/logs/langgraph_prune.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] Starting LangGraph contract pruning..." >> "$LOG_FILE"

cd /home/sieve-pub/public-workspace/octoagent/backend

# Run prune via Python
.venv/bin/python3 -c "
import sys
sys.path.insert(0, '.')
from src.agents.runtime import get_langgraph_workflow_contract_service

contract = get_langgraph_workflow_contract_service()
result = contract.prune(
    max_checkpoints_per_thread=20,
    max_runs_per_thread=100,
)

print(f'Pruning complete: {result}')
" >> "$LOG_FILE" 2>&1

echo "[$TIMESTAMP] Pruning finished." >> "$LOG_FILE"
