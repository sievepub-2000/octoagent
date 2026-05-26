#!/usr/bin/env bash
# octoagent-watchdog.sh — lightweight health watcher
#
# Probes the four canonical local ports (nginx, gateway, langgraph, frontend)
# every CHECK_INTERVAL seconds. After CONSECUTIVE_FAILS unhealthy rounds for
# any port, requests a single restart of octoagent-local.service. Logs every
# incident (probe failure + restart attempt + outcome) to JSONL so the
# self-evolution layer can mine recovery patterns later.
#
# Designed to be run manually, from cron, or as a tiny systemd unit. Safe to
# Ctrl-C; no daemonization, no PID files.
#
# Env knobs:
#   OCTO_WATCHDOG_INTERVAL          seconds between probes (default 30)
#   OCTO_WATCHDOG_FAIL_THRESHOLD    consecutive fails before recovery (default 3)
#   OCTO_WATCHDOG_COOLDOWN          seconds to wait after a restart before
#                                   resuming probing (default 90)
#   OCTO_WATCHDOG_LOG               path to incident JSONL log
#   OCTO_WATCHDOG_ONESHOT=1         run a single probe round and exit
#
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"

CHECK_INTERVAL="${OCTO_WATCHDOG_INTERVAL:-30}"
FAIL_THRESHOLD="${OCTO_WATCHDOG_FAIL_THRESHOLD:-3}"
COOLDOWN="${OCTO_WATCHDOG_COOLDOWN:-90}"
LOG_FILE="${OCTO_WATCHDOG_LOG:-$LOG_DIR/watchdog.jsonl}"
SERVICE="${OCTO_WATCHDOG_SERVICE:-octoagent-local.service}"

# port -> probe-url
declare -A PROBES=(
  [19800]="http://127.0.0.1:19800/"
  [19802]="http://127.0.0.1:19802/health"
  [19804]="http://127.0.0.1:19804/info"
  [19806]="http://127.0.0.1:19806/"
)

# fail counters keyed by port
declare -A FAILS=( [19800]=0 [19802]=0 [19804]=0 [19806]=0 )

log_event() {
  local kind="$1"; shift
  local extra="$1"; shift || true
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
  printf '{"ts":"%s","kind":"%s",%s}\n' "$ts" "$kind" "$extra" >> "$LOG_FILE"
}

probe_one() {
  local port="$1"
  local url="${PROBES[$port]}"
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$url" 2>/dev/null || echo 000)"
  # any 2xx/3xx counts as healthy
  if [[ "$code" =~ ^[23] ]]; then
    if (( FAILS[$port] > 0 )); then
      log_event "recovered" "\"port\":$port,\"code\":\"$code\",\"prev_fails\":${FAILS[$port]}"
    fi
    FAILS[$port]=0
    return 0
  fi
  FAILS[$port]=$(( FAILS[$port] + 1 ))
  log_event "probe_fail" "\"port\":$port,\"code\":\"$code\",\"fails\":${FAILS[$port]},\"threshold\":$FAIL_THRESHOLD"
  return 1
}

trigger_recovery() {
  local trip_port="$1"
  local trip_fails="$2"
  log_event "recovery_start" "\"trip_port\":$trip_port,\"trip_fails\":$trip_fails,\"service\":\"$SERVICE\""
  local rc=0
  if sudo -n systemctl restart "$SERVICE" 2>/dev/null; then
    log_event "recovery_invoked" "\"method\":\"systemctl\",\"rc\":0"
  else
    rc=$?
    log_event "recovery_failed" "\"method\":\"systemctl\",\"rc\":$rc"
    return $rc
  fi
  # reset counters, sleep cooldown so probes don't trigger another restart
  for p in "${!FAILS[@]}"; do FAILS[$p]=0; done
  sleep "$COOLDOWN"
  log_event "cooldown_done" "\"cooldown_s\":$COOLDOWN"
}

run_round() {
  local any_trip=0
  local trip_port=0
  local trip_fails=0
  for port in "${!PROBES[@]}"; do
    if ! probe_one "$port"; then
      if (( FAILS[$port] >= FAIL_THRESHOLD )); then
        any_trip=1
        trip_port=$port
        trip_fails=${FAILS[$port]}
      fi
    fi
  done
  if (( any_trip == 1 )); then
    trigger_recovery "$trip_port" "$trip_fails"
  fi
}

log_event "started" "\"interval_s\":$CHECK_INTERVAL,\"threshold\":$FAIL_THRESHOLD,\"cooldown_s\":$COOLDOWN,\"service\":\"$SERVICE\""

if [[ "${OCTO_WATCHDOG_ONESHOT:-0}" = "1" ]]; then
  run_round
  log_event "oneshot_done" "\"fails\":{\"19800\":${FAILS[19800]},\"19802\":${FAILS[19802]},\"19804\":${FAILS[19804]},\"19806\":${FAILS[19806]}}"
  exit 0
fi

trap 'log_event "stopped" "\"reason\":\"signal\""; exit 0' INT TERM

while true; do
  run_round
  sleep "$CHECK_INTERVAL"
done
