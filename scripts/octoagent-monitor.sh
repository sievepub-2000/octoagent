#!/usr/bin/env bash
# OctoAgent System Monitor
set -euo pipefail
trap 'echo "ERROR: $0 failed at line $LINENO" >> /var/log/octoagent_errors.log; exit 1' ERR


REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== OctoAgent System Status ==="
echo "Date: $(date)"
echo "Project: $REPO_ROOT"
echo ""

echo "--- CPU ---"
echo "Load: $(cat /proc/loadavg)"
echo "CPU Governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"
echo ""

echo "--- Memory ---"
free -h | grep -E 'Mem|Swap'
echo ""

echo "--- Disk ---"
df -h "$REPO_ROOT" | tail -1
echo ""

echo "--- GPU ---"
nvidia-smi --query-gpu=temperature.gpu,power.draw,memory.used --format=csv,noheader 2>/dev/null
echo ""

echo "--- Services ---"
systemctl is-active octoagent-local.service 2>/dev/null || true
echo ""

echo "--- Top Processes ---"
ps aux --sort=-%cpu | head -6
echo ""

echo "--- Network ---"
echo "WiFi Signal: $(nmcli -t -f SIGNAL device wifi list ifname wlP9s9 2>/dev/null | head -1)"
echo "Default Route: $(ip route show default | head -1)"
