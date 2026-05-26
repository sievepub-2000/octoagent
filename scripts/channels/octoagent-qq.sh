#!/usr/bin/env bash
# Dedicated QQ/NapCat channel launcher. Systemd calls `run`; operators use start/stop/status.

set -euo pipefail

export PATH="/snap/bin:/usr/local/bin:/usr/bin:/usr/sbin:$PATH"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE_NAME="octoagent-qq.service"
HEALTH_INTERVAL_SECONDS="${OCTOAGENT_QQ_HEALTH_INTERVAL_SECONDS:-30}"
LOG_FILE="$REPO_ROOT/runtime/logs/octoagent-qq-supervisor.log"
BRIDGE_HEALTH_URL="${QQ_BRIDGE_HEALTH_URL:-http://127.0.0.1:19814/health}"

usage() {
    cat <<USAGE
Usage: $0 <run|start|stop|restart|status>
  run      Start QQ/NapCat and keep a foreground supervisor for systemd.
  start    Start ${SERVICE_NAME} through systemd.
  stop     Stop ${SERVICE_NAME} through systemd.
  restart  Restart ${SERVICE_NAME} through systemd.
  status   Show ${SERVICE_NAME} status.
USAGE
}

systemctl_cmd() {
    if [ "$(id -u)" -eq 0 ]; then
        systemctl "$@"
    else
        sudo systemctl "$@"
    fi
}

stop_runtime() {
    "$REPO_ROOT/scripts/channels/stop-external-bridges.sh" || true
}

bridge_healthy() {
    curl -fsS "$BRIDGE_HEALTH_URL" >/dev/null 2>&1
}

start_runtime() {
    "$REPO_ROOT/scripts/channels/start-external-bridges.sh"
}

run_supervised() {
    cd "$REPO_ROOT"
    mkdir -p "$REPO_ROOT/runtime/logs" "$REPO_ROOT/runtime/pids"
    echo "===== OctoAgent QQ service run $(date -Is) =====" >> "$LOG_FILE"

    start_runtime >> "$LOG_FILE" 2>&1
    trap 'echo "$(date -Is) QQ supervisor stopping" >> "$LOG_FILE"; stop_runtime >> "$LOG_FILE" 2>&1; exit 0' INT TERM

    while true; do
        if ! bridge_healthy; then
            echo "$(date -Is) QQ bridge health failed; restarting bridge stack" >> "$LOG_FILE"
            stop_runtime >> "$LOG_FILE" 2>&1 || true
            start_runtime >> "$LOG_FILE" 2>&1 || true
        fi
        sleep "$HEALTH_INTERVAL_SECONDS"
    done
}

case "${1:-run}" in
    run) run_supervised ;;
    start) systemctl_cmd start "$SERVICE_NAME" ;;
    stop) systemctl_cmd stop "$SERVICE_NAME" ;;
    restart) systemctl_cmd restart "$SERVICE_NAME" ;;
    status) systemctl status "$SERVICE_NAME" --no-pager ;;
    --help|-h|help) usage ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
esac
