#!/usr/bin/env bash
# OctoAgent service/operator launcher.
# Systemd calls `run`; operators use start/stop/restart/status.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="octoagent-local.service"
ENTRY_PORT="${OCTO_NGINX_PORT:-19800}"
HEALTH_INTERVAL_SECONDS="${OCTOAGENT_HEALTH_INTERVAL_SECONDS:-30}"
STARTUP_LOG="$REPO_ROOT/runtime/logs/octoagent-startup.log"
SUPERVISOR_LOG="$REPO_ROOT/runtime/logs/octoagent-supervisor.log"

export PATH="/snap/bin:/usr/bin:/usr/sbin:/bin:$REPO_ROOT/scripts:$PATH"
export TMPDIR="${TMPDIR:-$REPO_ROOT/tmp}"
export OCTOAGENT_PYTHON_BIN="${OCTOAGENT_PYTHON_BIN:-$REPO_ROOT/backend/.venv/bin/python}"
export OCTOAGENT_TOOLS_DIR="${OCTOAGENT_TOOLS_DIR:-$REPO_ROOT/runtime/tools}"
export NPM_CONFIG_CACHE="${NPM_CONFIG_CACHE:-$REPO_ROOT/runtime/tools/npm-cache}"
export npm_config_cache="$NPM_CONFIG_CACHE"
export TRIVY_CACHE_DIR="${TRIVY_CACHE_DIR:-$REPO_ROOT/runtime/tools/trivy-cache}"

usage() {
    cat <<USAGE
Usage: $0 <run|start|stop|restart|status|stop-runtime|open>
  run          Start OctoAgent and keep a foreground health supervisor for systemd.
  start        Start ${SERVICE_NAME} through systemd.
  stop         Stop ${SERVICE_NAME} through systemd.
  restart      Restart ${SERVICE_NAME} through systemd.
  status       Show ${SERVICE_NAME} status.
  stop-runtime Stop OctoAgent child services directly; used by systemd ExecStop.
  open         Open the local WebUI after it is ready.
USAGE
}

systemctl_cmd() {
    if [ "$(id -u)" -eq 0 ]; then
        systemctl "$@"
    else
        sudo systemctl "$@"
    fi
}

wait_ready() {
    local elapsed=0
    while [ "$elapsed" -lt 120 ]; do
        if curl -fsS "http://127.0.0.1:${ENTRY_PORT}/api/models" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 1
}

stop_runtime() {
    cd "$REPO_ROOT"
    "$REPO_ROOT/scripts/stop-services.sh"
}

prepare_systemd_runtime() {
    local runtime_user
    local runtime_group
    local next_dir="$REPO_ROOT/frontend/.next"

    runtime_user="$(stat -c '%U' "$REPO_ROOT")"
    runtime_group="$(stat -c '%G' "$REPO_ROOT")"
    mkdir -p "$REPO_ROOT/tmp" "$REPO_ROOT/runtime/logs"

    if [ -d "$next_dir" ] && command -v sudo >/dev/null 2>&1; then
        sudo -n /usr/bin/find "$next_dir" \( -not -user "$runtime_user" -o -not -group "$runtime_group" \) \
            -exec chown "$runtime_user:$runtime_group" {} + 2>/dev/null || true
    fi

    if [ -x "$REPO_ROOT/scripts/repair-runtime-permissions.sh" ] && command -v sudo >/dev/null 2>&1; then
        sudo -n "$REPO_ROOT/scripts/repair-runtime-permissions.sh" 2>/dev/null || true
    fi
}

run_supervised() {
    cd "$REPO_ROOT"
    prepare_systemd_runtime
    echo "===== OctoAgent service run $(date -Is) =====" >> "$SUPERVISOR_LOG"

    "$REPO_ROOT/scripts/start-daemon.sh" --prod > "$STARTUP_LOG" 2>&1
    if ! wait_ready; then
        echo "$(date -Is) startup health check failed on port ${ENTRY_PORT}" >> "$SUPERVISOR_LOG"
        tail -80 "$STARTUP_LOG" >> "$SUPERVISOR_LOG" 2>/dev/null || true
        stop_runtime || true
        exit 1
    fi

    echo "$(date -Is) OctoAgent ready on http://127.0.0.1:${ENTRY_PORT}" >> "$SUPERVISOR_LOG"
    trap 'echo "$(date -Is) supervisor stopping" >> "$SUPERVISOR_LOG"; stop_runtime || true; exit 0' INT TERM

    while true; do
        sleep "$HEALTH_INTERVAL_SECONDS"
        if ! curl -fsS "http://127.0.0.1:${ENTRY_PORT}/api/models" >/dev/null 2>&1; then
            echo "$(date -Is) health check failed on port ${ENTRY_PORT}; exiting for systemd restart" >> "$SUPERVISOR_LOG"
            stop_runtime || true
            exit 1
        fi
    done
}

open_webui() {
    cd "$REPO_ROOT"
    echo "???? OctoAgent WebUI..."
    if ! wait_ready; then
        echo "? ??????????: $STARTUP_LOG"
        exit 1
    fi
    echo "? OctoAgent ?????????????..."
    su - sieve-pub -c "xdg-open http://localhost:${ENTRY_PORT}" 2>/dev/null &
    echo "? ??????: http://localhost:${ENTRY_PORT}"
}

case "${1:-run}" in
    run) run_supervised ;;
    start) systemctl_cmd start "$SERVICE_NAME" ;;
    stop) systemctl_cmd stop "$SERVICE_NAME" ;;
    restart) systemctl_cmd restart "$SERVICE_NAME" ;;
    status) systemctl status "$SERVICE_NAME" --no-pager ;;
    stop-runtime) stop_runtime ;;
    open) open_webui ;;
    --help|-h|help) usage ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
esac
