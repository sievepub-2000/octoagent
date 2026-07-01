#!/usr/bin/env bash
set -euo pipefail
trap 'echo "ERROR: $0 failed at line $LINENO" >> /var/log/octoagent_errors.log; exit 1' ERR


REPO_URL="${OCTOAGENT_REPO_URL:-https://github.com/sievepub-2000/octoagent.git}"
BRANCH="${OCTOAGENT_BRANCH:-main}"
PREFIX="${OCTOAGENT_HOME:-$HOME/octoagent}"
START_AFTER=1
BUILD=1
PULL=0
WAIT_SECONDS=240

usage() {
    cat <<USAGE
Usage: install-docker.sh [options]

Docker-only installer for Linux and macOS. Windows users can run scripts/install-docker.ps1.

Options:
  --prefix PATH      Install or use checkout at PATH (default: $PREFIX)
  --repo URL         Git repository URL (default: $REPO_URL)
  --branch NAME      Git branch (default: $BRANCH)
  --no-start         Prepare files but do not start containers
  --no-build         Do not build images before start
  --pull             Pull base images before build/start
  --wait SECONDS     Health-check timeout (default: $WAIT_SECONDS)
  --help, -h         Show this help
USAGE
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --prefix) PREFIX="${2:?--prefix requires a path}"; shift 2 ;;
        --repo) REPO_URL="${2:?--repo requires a URL}"; shift 2 ;;
        --branch) BRANCH="${2:?--branch requires a branch}"; shift 2 ;;
        --no-start) START_AFTER=0; shift ;;
        --no-build) BUILD=0; shift ;;
        --pull) PULL=1; shift ;;
        --wait) WAIT_SECONDS="${2:?--wait requires seconds}"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }
}

compose() {
    docker compose --env-file .env.docker -f compose.yaml "$@"
}

random_secret() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 48
    else
        python3 - <<'PY'
import base64, os
print(base64.b64encode(os.urandom(48)).decode())
PY
    fi
}

ensure_checkout() {
    if [ -d "$PREFIX/.git" ]; then
        cd "$PREFIX"
        git fetch origin "$BRANCH"
        git checkout "$BRANCH"
        git pull --ff-only origin "$BRANCH"
    elif [ -e "$PREFIX" ] && [ "$(find "$PREFIX" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)" -gt 0 ]; then
        echo "Prefix exists and is not an empty git checkout: $PREFIX" >&2
        exit 1
    else
        mkdir -p "$(dirname "$PREFIX")"
        git clone --branch "$BRANCH" "$REPO_URL" "$PREFIX"
        cd "$PREFIX"
    fi
}

prepare_files() {
    [ -f config.yaml ] || cp config.example.yaml config.yaml
    [ -f .env.docker ] || cp .env.docker.example .env.docker
    if grep -q 'replace-with-a-long-random-secret' .env.docker; then
        secret="$(random_secret)"
        if sed --version >/dev/null 2>&1; then
            sed -i "s#replace-with-a-long-random-secret#$secret#" .env.docker
        else
            sed -i '' "s#replace-with-a-long-random-secret#$secret#" .env.docker
        fi
    fi
    mkdir -p logs runtime/cache runtime/logs runtime/system_tools workspace/env workspace/default tmp
}

wait_for_http() {
    local url="$1"
    local deadline=$((SECONDS + WAIT_SECONDS))
    while [ "$SECONDS" -lt "$deadline" ]; do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 3
    done
    echo "Timed out waiting for $url" >&2
    compose ps >&2 || true
    compose logs --tail=120 nginx gateway langgraph frontend >&2 || true
    return 1
}

require_cmd git
require_cmd docker
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 is required. Install Docker Desktop or the docker compose plugin." >&2
    exit 1
fi

ensure_checkout
prepare_files

if [ "$PULL" = "1" ]; then
    compose pull --ignore-buildable || true
fi

if [ "$START_AFTER" = "1" ]; then
    if [ "$BUILD" = "1" ]; then
        compose up -d --build --remove-orphans
    else
        compose up -d --remove-orphans
    fi
    port="$(grep -E '^OCTO_NGINX_PORT=' .env.docker | tail -1 | cut -d= -f2 | tr -d '\r')"
    port="${port:-19800}"
    wait_for_http "http://127.0.0.1:${port}/health"
    echo "OctoAgent Docker is ready: http://127.0.0.1:${port}"
else
    echo "OctoAgent Docker files are ready in $PREFIX. Start with: docker compose --env-file .env.docker -f compose.yaml up -d --build"
fi
