#!/bin/bash
# Memory baseline script for LangGraph dev mode
set -euo pipefail
LOG_FILE="mem_baseline_$(date +%Y%m%d_%H%M%S).log"
{
echo "Starting memory baseline at $(date)"
# cold start RSS
echo "Cold start RSS:"
ps -o rss= -C langgraph_cli || echo "not running"
# idle 10 min
echo "Idling for 10 minutes..."
sleep 600
echo "After 10 min idle RSS:"
ps -o rss= -C langgraph_cli || echo "not running"
# long research (placeholder)
echo "Running long research task (simulated)..."
# simulate with a dummy command that runs for 2 minutes
timeout 120 bash -c "while true; do sleep 1; done" &
LANG_PID=$!
sleep 120
kill $LANG_PID 2>/dev/null || true
echo "After long research RSS:"
ps -o rss= -C langgraph_cli || echo "not running"
# file editing (placeholder)
echo "Running file editing task (simulated)..."
timeout 60 bash -c "while true; do sleep 1; done" &
EDIT_PID=$!
sleep 60
kill $EDIT_PID 2>/dev/null || true
echo "After file editing RSS:"
ps -o rss= -C langgraph_cli || echo "not running"
# 5 continuation resumes (placeholder)
echo "Simulating 5 continuation resumes..."
for i in {1..5}; do
  timeout 30 bash -c "while true; do sleep 1; done" &
  CONT_PID=$!
  sleep 30
  kill $CONT_PID 2>/dev/null || true
done
echo "After continuation resumes RSS:"
ps -o rss= -C langgraph_cli || echo "not running"
echo "Baseline completed at $(date)"
} | tee "$LOG_FILE"
echo "Log saved to $LOG_FILE"
