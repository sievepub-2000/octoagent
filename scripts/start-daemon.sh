#!/usr/bin/env bash
#
# start-daemon.sh - Start all OctoAgent development services in daemon mode
#
# This script starts OctoAgent services in the background without keeping
# the terminal connection. Logs are written to separate files.
#
# Must be run from the repo root directory.

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

source "$REPO_ROOT/scripts/port-layout.sh"

if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +a
fi

# Use the repository-owned setup snapshot so local services do not
# drift to stale user-level setup_state.json from another checkout.
export OCTO_AGENT_SETUP_STATE_FILE="${OCTO_AGENT_SETUP_STATE_FILE:-$REPO_ROOT/workspace/env/setup.json}"
export OCTOAGENT_RUNTIME_CONFIG_DIR="${OCTOAGENT_RUNTIME_CONFIG_DIR:-$REPO_ROOT/backend/runtime}"
export PYTHONDONTWRITEBYTECODE="${PYTHONDONTWRITEBYTECODE:-1}"
export TMPDIR="${TMPDIR:-$REPO_ROOT/tmp}"
export OCTOAGENT_PYTHON_BIN="${OCTOAGENT_PYTHON_BIN:-$REPO_ROOT/backend/.venv/bin/python}"
if [ ! -x "$OCTOAGENT_PYTHON_BIN" ]; then
    echo "✗ OctoAgent backend venv not found at $OCTOAGENT_PYTHON_BIN. Run backend dependency installation first." >&2
    exit 1
fi
export VIRTUAL_ENV="$REPO_ROOT/backend/.venv"
export PATH="$VIRTUAL_ENV/bin:/snap/bin:/usr/bin:/usr/sbin:/bin:$REPO_ROOT/scripts:$PATH"
if [ "${OCTO_USE_EXTERNAL_CACHE:-0}" != "1" ]; then
    export XDG_CACHE_HOME="$REPO_ROOT/runtime/cache/xdg"
    export UV_CACHE_DIR="$REPO_ROOT/runtime/cache/uv"
    export PIP_CACHE_DIR="$REPO_ROOT/runtime/cache/pip"
    export PLAYWRIGHT_BROWSERS_PATH="$REPO_ROOT/runtime/cache/ms-playwright"
    export HF_HOME="$REPO_ROOT/runtime/cache/huggingface"
    export SENTENCE_TRANSFORMERS_HOME="$REPO_ROOT/runtime/cache/sentence_transformers"
else
    export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$REPO_ROOT/runtime/cache/xdg}"
    export UV_CACHE_DIR="${UV_CACHE_DIR:-$REPO_ROOT/runtime/cache/uv}"
    export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$REPO_ROOT/runtime/cache/pip}"
    export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$REPO_ROOT/runtime/cache/ms-playwright}"
    export HF_HOME="${HF_HOME:-$REPO_ROOT/runtime/cache/huggingface}"
    export SENTENCE_TRANSFORMERS_HOME="${SENTENCE_TRANSFORMERS_HOME:-$REPO_ROOT/runtime/cache/sentence_transformers}"
fi
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export OCTOAGENT_MANAGE_EXTERNAL_BRIDGES="${OCTOAGENT_MANAGE_EXTERNAL_BRIDGES:-1}"
export OCTOAGENT_MANAGE_TTYD="${OCTOAGENT_MANAGE_TTYD:-1}"

# Local daemon mode should use the current ingress origin in browser code unless
# an operator explicitly opts into fixed public URLs. Stale localhost URLs break
# remote LAN browsers because localhost then points at the viewer's machine.
if [ "${OCTO_USE_EXPLICIT_NEXT_PUBLIC_URLS:-0}" != "1" ]; then
    export NEXT_PUBLIC_BACKEND_BASE_URL=""
    export NEXT_PUBLIC_LANGGRAPH_BASE_URL=""
fi
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$UV_CACHE_DIR" "$PIP_CACHE_DIR" "$PLAYWRIGHT_BROWSERS_PATH" "$HF_HOME" "$SENTENCE_TRANSFORMERS_HOME"

repair_runtime_permissions() {
    local runtime_user
    local runtime_group
    local system_tools_root="$REPO_ROOT/runtime/system_tools"

    runtime_user="$(id -un)"
    runtime_group="$(id -gn)"
    mkdir -p "$system_tools_root/html_to_canvas" "$system_tools_root/flipbook" 2>/dev/null || true

    if [ "$(id -u)" -eq 0 ]; then
        chown -R "$runtime_user:$runtime_group" "$system_tools_root"
    elif command -v sudo >/dev/null 2>&1; then
        sudo -n mkdir -p "$system_tools_root/html_to_canvas" "$system_tools_root/flipbook" 2>/dev/null || true
        sudo -n chown -R "$runtime_user:$runtime_group" "$system_tools_root" 2>/dev/null || true
    fi
    chmod -R u+rwX,go+rX "$system_tools_root" 2>/dev/null || true
}

repair_runtime_permissions

NGINX_CONFIG_TEMPLATE="$REPO_ROOT/docker/nginx/nginx.local.conf.template"
NGINX_CONFIG_RENDERED="$REPO_ROOT/tmp/nginx.local.conf"
export OCTO_NGINX_TEMP_ROOT="${OCTO_NGINX_TEMP_ROOT:-$REPO_ROOT/tmp/nginx-$NGINX_PORT}"

DEV_MODE=true

show_usage() {
    echo "Usage: $0 [--dev|--prod]"
    echo "  --dev   Start all services in daemon development mode (default)"
    echo "  --prod  Start all services in daemon production mode"
}

for arg in "$@"; do
    case "$arg" in
        --help|-h) show_usage; exit 0 ;;
        --dev) DEV_MODE=true ;;
        --prod) DEV_MODE=false ;;
        *) echo "Unknown argument: $arg"; show_usage; exit 1 ;;
    esac
done

if [ "${OCTOAGENT_MANAGED_BY_SYSTEMD:-0}" != "1" ] \
    && [ "${OCTOAGENT_ALLOW_MANUAL_START:-0}" != "1" ] \
    && command -v systemctl >/dev/null 2>&1 \
    && systemctl is-enabled --quiet octoagent-local.service 2>/dev/null \
    && systemctl is-active --quiet octoagent-local.service 2>/dev/null; then
    echo "✗ octoagent-local.service is already the active startup owner." >&2
    echo "  Use: sudo systemctl restart octoagent-local.service" >&2
    echo "  For an intentional manual takeover, stop the unit first or set OCTOAGENT_ALLOW_MANUAL_START=1." >&2
    exit 1
fi

prepare_nginx_temp_dirs() {
    local nginx_tmp_root="$OCTO_NGINX_TEMP_ROOT"
    local dir

    mkdir -p "$nginx_tmp_root" \
        "$nginx_tmp_root/client_body" \
        "$nginx_tmp_root/proxy" \
        "$nginx_tmp_root/fastcgi" \
        "$nginx_tmp_root/uwsgi" \
        "$nginx_tmp_root/scgi"

    # Nginx workers can run as nobody/nogroup even when the launcher runs as
    # the repo owner. Keep local temp paths under /tmp and writable by the
    # worker so request bodies do not fail before reaching upstream services.
    for dir in "$nginx_tmp_root" "$nginx_tmp_root/client_body" "$nginx_tmp_root/proxy" "$nginx_tmp_root/fastcgi" "$nginx_tmp_root/uwsgi" "$nginx_tmp_root/scgi"; do
        if chmod 1777 "$dir" 2>/dev/null; then
            continue
        fi
        rm -rf "$dir"
        mkdir -p "$dir"
        chmod 1777 "$dir"
    done
}

mkdir -p "$REPO_ROOT/tmp"
prepare_nginx_temp_dirs
"$OCTOAGENT_PYTHON_BIN" "$REPO_ROOT/scripts/render_nginx_config.py" \
    "$NGINX_CONFIG_TEMPLATE" \
    "$NGINX_CONFIG_RENDERED"

kill_port_owners() {
    local port="$1"

    if command -v fuser >/dev/null 2>&1; then
        fuser -k "${port}/tcp" 2>/dev/null || true
        return
    fi

    if command -v lsof >/dev/null 2>&1; then
        lsof -ti tcp:"$port" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
        return
    fi

    if command -v ss >/dev/null 2>&1; then
        ss -ltnp "( sport = :$port )" 2>/dev/null \
            | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' \
            | xargs -r kill -9 2>/dev/null || true
    fi
}

wait_for_start_port_free() {
    local port="$1"
    local label="$2"

    for _ in $(seq 1 20); do
        if ! ss -ltn "( sport = :$port )" 2>/dev/null | grep -q ":$port"; then
            return 0
        fi
        kill_port_owners "$port"
        sleep 0.5
    done

    echo "✗ $label port $port is still occupied before startup." >&2
    ss -ltnp "( sport = :$port )" 2>/dev/null >&2 || true
    return 1
}

is_start_port_listening() {
    local port="$1"

    if command -v lsof >/dev/null 2>&1; then
        if lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
            return 0
        fi
    fi

    if command -v ss >/dev/null 2>&1; then
        if ss -ltn "( sport = :$port )" 2>/dev/null | tail -n +2 | grep -q .; then
            return 0
        fi
    fi

    if command -v timeout >/dev/null 2>&1; then
        timeout 1 bash -c "exec 3<>/dev/tcp/127.0.0.1/$port" >/dev/null 2>&1
        return $?
    fi

    return 1
}

wait_for_service_port() {
    local pid="$1"
    local port="$2"
    local timeout_seconds="$3"
    local service="$4"
    local elapsed=0

    while ! is_start_port_listening "$port"; do
        if ! kill -0 "$pid" 2>/dev/null; then
            printf "\r  %-60s\r" ""
            echo "✗ $service launcher exited before port $port was ready."
            return 2
        fi
        if [ "$elapsed" -ge "$timeout_seconds" ]; then
            printf "\r  %-60s\r" ""
            echo "✗ $service failed to start on port $port after ${timeout_seconds}s"
            return 1
        fi
        printf "\r  Waiting for %s on port %s... %ds" "$service" "$port" "$elapsed"
        sleep 1
        elapsed=$((elapsed + 1))
    done

    printf "\r  %-60s\r" ""
    return 0
}

# ── Stop existing services ────────────────────────────────────────────────────

echo "Stopping existing services if any..."
OCTOAGENT_MANAGE_EXTERNAL_BRIDGES="$OCTOAGENT_MANAGE_EXTERNAL_BRIDGES" "$REPO_ROOT/scripts/stop-services.sh" >/dev/null || true
sleep 1
wait_for_start_port_free "$LANGGRAPH_PORT" "LangGraph"
wait_for_start_port_free "$GATEWAY_PORT" "Gateway"
wait_for_start_port_free "$FRONTEND_PORT" "Frontend"
wait_for_start_port_free "$NGINX_PORT" "Nginx"
if [ "$OCTOAGENT_MANAGE_TTYD" = "1" ]; then
    wait_for_start_port_free "$TTYD_PORT" "ttyd"
fi

# ── Banner ────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
if $DEV_MODE; then
    echo " Starting OctoAgent in Daemon Mode (DEV)"
else
    echo " Starting OctoAgent in Daemon Mode (PROD)"
fi
echo "=========================================="
echo ""

# ── Config check ─────────────────────────────────────────────────────────────
#
# Resolution order (matches backend/src/runtime/config/app_config.py since
# 2026-05-27): explicit env path → runtime/config/config.yaml (preferred) →
# backend/config.yaml / config.yaml (deprecated back-compat). When a path is
# found we export OCTO_AGENT_CONFIG_PATH so every spawned Python process
# resolves the same file even if its cwd differs.

if [ -n "$OCTO_AGENT_CONFIG_PATH" ] && [ -f "$OCTO_AGENT_CONFIG_PATH" ]; then
    : "already exported by caller"
elif [ -f "$REPO_ROOT/runtime/config/config.yaml" ]; then
    export OCTO_AGENT_CONFIG_PATH="$REPO_ROOT/runtime/config/config.yaml"
elif [ -f "$REPO_ROOT/backend/config.yaml" ]; then
    export OCTO_AGENT_CONFIG_PATH="$REPO_ROOT/backend/config.yaml"
elif [ -f "$REPO_ROOT/config.yaml" ]; then
    export OCTO_AGENT_CONFIG_PATH="$REPO_ROOT/config.yaml"
else
    echo "✗ No OctoAgent config file found."
    echo "  Checked these locations:"
    echo "    - \$OCTO_AGENT_CONFIG_PATH (when set)"
    echo "    - $REPO_ROOT/runtime/config/config.yaml   (preferred since 2026-05-27)"
    echo "    - $REPO_ROOT/backend/config.yaml          (back-compat)"
    echo "    - $REPO_ROOT/config.yaml                  (back-compat)"
    echo ""
    echo "  Run 'make config' from the repo root to generate runtime/config/config.yaml,"
    echo "  then set required model API keys in .env or your config file."
    exit 1
fi

# ── Cleanup on failure ───────────────────────────────────────────────────────

cleanup_on_failure() {
    echo "Failed to start services, cleaning up..."
    "$REPO_ROOT/scripts/stop-services.sh" >/dev/null || true
    echo "✓ Cleanup complete"
}

trap cleanup_on_failure INT TERM

assert_process_alive() {
    local pid="$1"
    local service="$2"
    local logfile="$3"
    if kill -0 "$pid" 2>/dev/null; then
        return 0
    fi

    echo "✗ $service launcher exited before the service was ready."
    if [ -f "$logfile" ]; then
        echo "  Last log output from $logfile:"
        tail -60 "$logfile"
    fi
    cleanup_on_failure
    exit 1
}

# ── Process launcher ─────────────────────────────────────────────────────────
start_detached() {
    local workdir="$1"
    local logfile="$2"
    shift 2

    if command -v setsid >/dev/null 2>&1; then
        nohup setsid bash -c 'cd "$1" && shift && exec "$@"' bash "$workdir" "$@" > "$logfile" 2>&1 &
    else
        nohup bash -c 'trap "" HUP; cd "$1" && shift && exec "$@"' bash "$workdir" "$@" > "$logfile" 2>&1 &
    fi
    echo $!
}

start_ttyd() {
    if [ "$OCTOAGENT_MANAGE_TTYD" != "1" ]; then
        echo "Skipping ttyd; managed externally."
        return 0
    fi
    if ! command -v ttyd >/dev/null 2>&1; then
        echo "Skipping ttyd; ttyd binary not found."
        return 0
    fi

    echo "Starting ttyd terminal bridge..."
    local ttyd_pid
    ttyd_pid=$(
        start_detached "$REPO_ROOT" "$REPO_ROOT/logs/ttyd.log" \
            ttyd --interface 127.0.0.1 --port "$TTYD_PORT" --writable --cwd "$REPO_ROOT" /bin/bash -l
    )
    printf '%s\n' "$ttyd_pid" > "$REPO_ROOT/runtime/pids/ttyd.pid"
    ./scripts/wait-for-port.sh "$TTYD_PORT" 20 "ttyd" || {
        echo "✗ ttyd failed to start. Last log output:"
        tail -60 logs/ttyd.log
        cleanup_on_failure
        exit 1
    }
    assert_process_alive "$ttyd_pid" "ttyd" "logs/ttyd.log"
    echo "✓ ttyd terminal bridge started on localhost:$TTYD_PORT"
}

# ── Python runner detection ───────────────────────────────────────────────────
LANGGRAPH_RUN=("$OCTOAGENT_PYTHON_BIN" -m langgraph_cli)
PY_RUN=("$OCTOAGENT_PYTHON_BIN" -m)

clean_frontend_build_dir() {
    local target="$REPO_ROOT/frontend/.next"
    local expected="$REPO_ROOT/frontend/.next"
    local resolved_target
    local resolved_expected

    resolved_target="$(realpath -m "$target")"
    resolved_expected="$(realpath -m "$expected")"
    if [ "$resolved_target" != "$resolved_expected" ]; then
        echo "ERROR: Refusing to clean unexpected frontend build directory: $resolved_target"
        exit 1
    fi
    # Sprint-1 patch: heal stray root-owned artifacts from past root-as-build runs.
    # Without this, plain `rm -rf` as the repo owner fails on root-owned files
    # and the systemd restart wedges (we hit this twice in 2026-05-13).
    if [ -d "$resolved_target" ]; then
        if command -v sudo >/dev/null 2>&1 && [ "$(id -u)" -ne 0 ]; then
            sudo -n /usr/bin/find "$resolved_target" -not -user "$(id -un)" -exec chown "$(id -un):$(id -gn)" {} + 2>/dev/null || true
        fi
    fi
    rm -rf "$resolved_target" 2>/dev/null || {
        echo "  clean_frontend_build_dir: rm failed once, retrying after chown attempt..."
        chown -R "$(id -un):$(id -gn)" "$resolved_target" 2>/dev/null || true
        rm -rf "$resolved_target"
    }
}

if $DEV_MODE; then
    if [ "${OCTO_FRONTEND_CLEAN_CACHE:-0}" = "1" ]; then
        echo "Cleaning frontend development cache..."
        clean_frontend_build_dir
    else
        echo "Preserving frontend development cache (set OCTO_FRONTEND_CLEAN_CACHE=1 to clean)."
    fi

    FRONTEND_DEV_ENGINE="${OCTO_FRONTEND_DEV_ENGINE:-turbo}"
    case "$FRONTEND_DEV_ENGINE" in
        webpack)
            FRONTEND_CMD=(pnpm exec next dev --webpack --hostname 127.0.0.1 --port "$FRONTEND_PORT")
            ;;
        turbo|turbopack)
            FRONTEND_CMD=(pnpm exec next dev --turbo --hostname 127.0.0.1 --port "$FRONTEND_PORT")
            ;;
        *)
            echo "✗ Unsupported OCTO_FRONTEND_DEV_ENGINE: $FRONTEND_DEV_ENGINE (expected turbo or webpack)"
            exit 1
            ;;
    esac
    if [ "${OCTO_LANGGRAPH_RELOAD:-0}" = "1" ]; then
        LANGGRAPH_EXTRA_FLAGS=()
    else
        LANGGRAPH_EXTRA_FLAGS=(--no-reload)
    fi
else
    FRONTEND_CMD=(
        env
        "BETTER_AUTH_SECRET=$("$OCTOAGENT_PYTHON_BIN" -c 'import secrets; print(secrets.token_hex(16))')"
        pnpm exec next start --hostname 127.0.0.1 --port "$FRONTEND_PORT"
    )
    LANGGRAPH_EXTRA_FLAGS=(--no-reload)
    # Frontend incremental build (octoagent B4): skip pnpm build when source
    # fingerprint matches the last successful build. Set OCTO_FRONTEND_FORCE_BUILD=1
    # to force a clean rebuild.
    frontend_src_hash() {
        (
            cd "$REPO_ROOT/frontend" || exit 1
            { find src public -type f \
                \( -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' \
                   -o -name '*.css' -o -name '*.json' -o -name '*.mjs' -o -name '*.html' \) \
                -print0 2>/dev/null | LC_ALL=C sort -z | xargs -0 sha256sum 2>/dev/null
              sha256sum package.json pnpm-lock.yaml next.config.js tsconfig.json \
                postcss.config.js components.json 2>/dev/null || true
            } | sha256sum | awk '{print $1}'
        )
    }

    frontend_runtime_src_hash() {
        (
            cd "$REPO_ROOT/frontend" || exit 1
            "$OCTOAGENT_PYTHON_BIN" - <<'PY'
from __future__ import annotations

import hashlib
from pathlib import Path

RUNTIME_EXTENSIONS = {".css", ".html", ".js", ".jsx", ".json", ".mjs", ".ts", ".tsx"}
CONFIG_FILES = [
    Path("package.json"),
    Path("pnpm-lock.yaml"),
    Path("next.config.js"),
    Path("tsconfig.json"),
    Path("postcss.config.js"),
    Path("components.json"),
]


def is_type_only_candidate(path: Path) -> bool:
    return path.suffix in {".ts", ".tsx"} and (
        path.name in {"type.ts", "types.ts"} or path.name.endswith("-types.ts")
    )


def has_runtime_ts_construct(path: Path) -> bool:
    if not is_type_only_candidate(path):
        return True
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return True
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue
        if stripped.startswith(("import type ", "export type ", "export interface ", "interface ", "type ")):
            continue
        if stripped.startswith("import "):
            return True
        if stripped.startswith("export {") and " from " in stripped:
            return True
        runtime_prefixes = (
            "export const ",
            "export let ",
            "export var ",
            "export function ",
            "export class ",
            "export enum ",
            "const ",
            "let ",
            "var ",
            "function ",
            "class ",
            "enum ",
        )
        if stripped.startswith(runtime_prefixes):
            return True
    return False


def iter_source_files():
    for root in (Path("src"), Path("public")):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in RUNTIME_EXTENSIONS and has_runtime_ts_construct(path):
                yield path
    for path in CONFIG_FILES:
        if path.exists():
            yield path


digest = hashlib.sha256()
for path in sorted(iter_source_files(), key=lambda item: item.as_posix()):
    digest.update(path.as_posix().encode("utf-8"))
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")
print(digest.hexdigest())
PY
        )
    }

    frontend_build_ready() {
        local required_file

        [ -f "$REPO_ROOT/frontend/.next/BUILD_ID" ] || return 1
        [ -f "$REPO_ROOT/frontend/.next/required-server-files.json" ] || return 1
        while IFS= read -r required_file; do
            [ -z "$required_file" ] && continue
            [ -e "$REPO_ROOT/frontend/$required_file" ] || {
                echo "  Missing frontend build artifact: $required_file"
                return 1
            }
        done < <(
            "$OCTOAGENT_PYTHON_BIN" - "$REPO_ROOT/frontend/.next/required-server-files.json" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
for item in payload.get("files", []):
    print(item)
PY
        )
    }

    FRONTEND_HASH_FILE="$REPO_ROOT/frontend/.next/.octoagent-src-hash"
    FRONTEND_RUNTIME_HASH_FILE="$REPO_ROOT/frontend/.next/.octoagent-runtime-src-hash"
    NEW_FRONTEND_HASH="$(frontend_src_hash)"
    NEW_FRONTEND_RUNTIME_HASH="$(frontend_runtime_src_hash)"
    SKIP_FRONTEND_BUILD=false
    SKIP_FRONTEND_BUILD_REASON=""
    if [ "${OCTO_FRONTEND_FORCE_BUILD:-0}" != "1" ] \
        && [ -f "$FRONTEND_HASH_FILE" ] \
        && [ "$(cat "$FRONTEND_HASH_FILE" 2>/dev/null)" = "$NEW_FRONTEND_HASH" ] \
        && frontend_build_ready; then
        SKIP_FRONTEND_BUILD=true
        SKIP_FRONTEND_BUILD_REASON="source hash unchanged"
    elif [ "${OCTO_FRONTEND_FORCE_BUILD:-0}" != "1" ] \
        && [ -f "$FRONTEND_RUNTIME_HASH_FILE" ] \
        && [ "$(cat "$FRONTEND_RUNTIME_HASH_FILE" 2>/dev/null)" = "$NEW_FRONTEND_RUNTIME_HASH" ] \
        && frontend_build_ready; then
        SKIP_FRONTEND_BUILD=true
        SKIP_FRONTEND_BUILD_REASON="runtime-impact hash unchanged"
    fi

    if $SKIP_FRONTEND_BUILD; then
        printf '%s\n' "$NEW_FRONTEND_HASH" > "$FRONTEND_HASH_FILE"
        printf '%s\n' "$NEW_FRONTEND_RUNTIME_HASH" > "$FRONTEND_RUNTIME_HASH_FILE"
        echo "OK Frontend build artifacts verified (${SKIP_FRONTEND_BUILD_REASON}; hash=${NEW_FRONTEND_HASH:0:12}, runtime=${NEW_FRONTEND_RUNTIME_HASH:0:12}); reusing existing .next build"
    else
        echo "Rebuilding frontend production assets..."
        (
            clean_frontend_build_dir
            cd frontend
            pnpm exec next build
        )
        printf '%s\n' "$NEW_FRONTEND_HASH" > "$FRONTEND_HASH_FILE"
        printf '%s\n' "$NEW_FRONTEND_RUNTIME_HASH" > "$FRONTEND_RUNTIME_HASH_FILE"
        echo "✓ Frontend production assets rebuilt (hash=${NEW_FRONTEND_HASH:0:12}, runtime=${NEW_FRONTEND_RUNTIME_HASH:0:12})"
    fi
fi

# ── Start services ────────────────────────────────────────────────────────────

mkdir -p logs runtime/pids runtime/logs

# LangChain/OpenAI/MCP model clients in this repo reject SOCKS-style proxy URLs,
# but external model providers may require the local HTTP proxy configured in .env.
# Keep SOCKS/FTP disabled while preserving HTTP(S)_PROXY for provider egress.
export ALL_PROXY=""
export all_proxy=""
export FTP_PROXY=""
export ftp_proxy=""
if $DEV_MODE && [ -z "${OCTO_SMTP_HOST:-}" ]; then
    # Local/dev installs without SMTP still need a usable registration flow.
    # The auth page displays this code only when the backend opts in here.
    export OCTO_AUTH_DEV_EXPOSE_CODES="${OCTO_AUTH_DEV_EXPOSE_CODES:-1}"
fi

# ── Start External Bridge Channels ────────────────────────────────────────────
if [ "$OCTOAGENT_MANAGE_EXTERNAL_BRIDGES" = "1" ]; then
    echo "Starting external bridge channels..."
    "$REPO_ROOT/scripts/channels/start-external-bridges.sh"
else
    echo "Skipping external bridge channels; managed by dedicated channel services."
fi

echo "Starting LangGraph server..."
LANGGRAPH_N_JOBS_PER_WORKER="${OCTO_LANGGRAPH_N_JOBS_PER_WORKER:-4}"
LANGGRAPH_PID=""
for attempt in 1 2; do
    LANGGRAPH_PID=$(
        start_detached "$REPO_ROOT/backend" "$REPO_ROOT/logs/langgraph.log" \
            env NO_COLOR=1 \
        BG_JOB_ISOLATED_LOOPS="${BG_JOB_ISOLATED_LOOPS:-true}" \
            "${LANGGRAPH_RUN[@]}" dev --no-browser --allow-blocking \
        --n-jobs-per-worker "$LANGGRAPH_N_JOBS_PER_WORKER" \
        --host 127.0.0.1 --port "$LANGGRAPH_PORT" "${LANGGRAPH_EXTRA_FLAGS[@]}"
    )
    if wait_for_service_port "$LANGGRAPH_PID" "$LANGGRAPH_PORT" 60 "LangGraph"; then
        break
    fi
    if [ "$attempt" -eq 1 ] && grep -qi "port $LANGGRAPH_PORT is already in use" logs/langgraph.log 2>/dev/null; then
        echo "LangGraph port $LANGGRAPH_PORT was still occupied during startup; clearing it and retrying once..."
        kill_port_owners "$LANGGRAPH_PORT"
        wait_for_start_port_free "$LANGGRAPH_PORT" "LangGraph"
        continue
    fi
    echo "✗ LangGraph failed to start. Last log output:"
    tail -60 logs/langgraph.log
    cleanup_on_failure
    exit 1
done
assert_process_alive "$LANGGRAPH_PID" "LangGraph" "logs/langgraph.log"
sleep 1
assert_process_alive "$LANGGRAPH_PID" "LangGraph" "logs/langgraph.log"
echo "✓ LangGraph server started on localhost:$LANGGRAPH_PORT"

echo "Starting Gateway API..."
GATEWAY_PID=$(
    start_detached "$REPO_ROOT/backend" "$REPO_ROOT/logs/gateway.log" \
        "${PY_RUN[@]}" uvicorn src.gateway.app:app \
        --host 127.0.0.1 --port "$GATEWAY_PORT"
)
./scripts/wait-for-port.sh $GATEWAY_PORT 30 "Gateway API" || {
    echo "✗ Gateway API failed to start. Last log output:"
    tail -60 logs/gateway.log
    cleanup_on_failure
    exit 1
}
assert_process_alive "$GATEWAY_PID" "Gateway API" "logs/gateway.log"
sleep 1
assert_process_alive "$GATEWAY_PID" "Gateway API" "logs/gateway.log"
echo "✓ Gateway API started on localhost:$GATEWAY_PORT"

echo "Starting Frontend..."
FRONTEND_PID=$(
    start_detached "$REPO_ROOT/frontend" "$REPO_ROOT/logs/frontend.log" \
        "${FRONTEND_CMD[@]}"
)
./scripts/wait-for-port.sh $FRONTEND_PORT 120 "Frontend" || {
    echo "✗ Frontend failed to start. Last log output:"
    tail -60 logs/frontend.log
    cleanup_on_failure
    exit 1
}
assert_process_alive "$FRONTEND_PID" "Frontend" "logs/frontend.log"
sleep 1
assert_process_alive "$FRONTEND_PID" "Frontend" "logs/frontend.log"
echo "✓ Frontend started on localhost:$FRONTEND_PORT"

echo "Starting Nginx reverse proxy..."
NGINX_PID=$(
    start_detached "$REPO_ROOT" "$REPO_ROOT/logs/nginx.log" \
        nginx -g "daemon off;" -c "$NGINX_CONFIG_RENDERED" -p "$REPO_ROOT"
)
./scripts/wait-for-port.sh $NGINX_PORT 10 "Nginx" || {
    echo "✗ Nginx failed to start. Last log output:"
    tail -60 logs/nginx.log
    cleanup_on_failure
    exit 1
}
assert_process_alive "$NGINX_PID" "Nginx" "logs/nginx.log"
sleep 1
assert_process_alive "$NGINX_PID" "Nginx" "logs/nginx.log"
echo "✓ Nginx started on localhost:$NGINX_PORT"

start_ttyd

# ── Ready ─────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
if $DEV_MODE; then
    echo " OctoAgent is running in daemon mode!"
else
    echo " OctoAgent is running in production daemon mode!"
fi
echo "=========================================="
echo ""
LOCAL_ENTRYPOINT="http://127.0.0.1:$NGINX_PORT"
PUBLIC_ENTRYPOINT="${OCTO_PUBLIC_BASE_URL:-$LOCAL_ENTRYPOINT}"
echo " 🌐 Local entrypoint: $LOCAL_ENTRYPOINT"
if [ "$PUBLIC_ENTRYPOINT" != "$LOCAL_ENTRYPOINT" ]; then
    echo " 🌍 Public entrypoint: $PUBLIC_ENTRYPOINT"
fi
echo " 📡 API Gateway: http://localhost:$NGINX_PORT/api/*"
echo " 🤖 LangGraph: http://localhost:$NGINX_PORT/api/langgraph/*"
echo ""
echo " 📋 Logs:"
echo " - LangGraph: logs/langgraph.log"
echo " - Gateway: logs/gateway.log"
echo " - Frontend: logs/frontend.log"
echo " - Nginx: logs/nginx.log"
if [ "$OCTOAGENT_MANAGE_TTYD" = "1" ]; then
    echo " - ttyd: logs/ttyd.log"
fi
echo ""
echo " 🛑 Stop daemon: make stop"
echo ""
