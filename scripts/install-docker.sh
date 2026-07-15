#!/usr/bin/env bash
set -euo pipefail
trap 'echo "ERROR: $0 failed at line $LINENO" >> "${TMPDIR:-/tmp}/octoagent_errors.log"; exit 1' ERR


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

random_hex_secret() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 24
    else
        python3 - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
    fi
}

ensure_checkout() {
    if [ -d "$PREFIX/.git" ]; then
        cd "$PREFIX"
        git fetch origin "$BRANCH"
        git checkout "$BRANCH"
        git pull --ff-only origin "$BRANCH"
    elif [ -f "$PREFIX/compose.yaml" ] && [ -f "$PREFIX/docker/Dockerfile.backend-prod" ]; then
        # Release archives intentionally have no .git directory. An explicit
        # prefix containing the packaged Compose markers is a valid checkout.
        cd "$PREFIX"
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
    mkdir -p runtime/config backend/runtime
    if [ ! -f runtime/config/config.yaml ]; then
        if [ -f config.yaml ]; then
            cp config.yaml runtime/config/config.yaml
        else
            cp config.example.yaml runtime/config/config.yaml
        fi
    fi
    if [ ! -f runtime/config/extensions_config.json ]; then
        if [ -f extensions_config.json ]; then
            cp extensions_config.json runtime/config/extensions_config.json
        else
            cp extensions_config.example.json runtime/config/extensions_config.json
        fi
    fi
    [ -f .env.docker ] || cp .env.docker.example .env.docker
    if grep -q 'replace-with-a-long-random-secret' .env.docker; then
        secret="$(random_secret)"
        if sed --version >/dev/null 2>&1; then
            sed -i "s#replace-with-a-long-random-secret#$secret#" .env.docker
        else
            sed -i '' "s#replace-with-a-long-random-secret#$secret#" .env.docker
        fi
    fi
    if grep -q '^POSTGRES_PASSWORD=octoagent-change-me$' .env.docker; then
        postgres_secret="$(random_hex_secret)"
        if sed --version >/dev/null 2>&1; then
            sed -i "s#^POSTGRES_PASSWORD=octoagent-change-me#POSTGRES_PASSWORD=$postgres_secret#" .env.docker
        else
            sed -i '' "s#^POSTGRES_PASSWORD=octoagent-change-me#POSTGRES_PASSWORD=$postgres_secret#" .env.docker
        fi
    fi
    mkdir -p logs runtime/cache runtime/langgraph runtime/logs runtime/secrets runtime/system_tools skills/custom workspace/env workspace/default tmp
    touch runtime/secrets/models.env
    chmod 600 .env.docker runtime/secrets/models.env
}

set_env_number() {
    local key="$1"
    local value="$2"
    local expression="s/^${key}=.*/${key}=${value}/"
    if grep -q "^${key}=" .env.docker; then
        if sed --version >/dev/null 2>&1; then
            sed -i "$expression" .env.docker
        else
            sed -i '' "$expression" .env.docker
        fi
    else
        printf '\n%s=%s\n' "$key" "$value" >> .env.docker
    fi
}

configure_container_identity() {
    local host_uid="${SUDO_UID:-$(id -u)}"
    local host_gid="${SUDO_GID:-$(id -g)}"
    local docker_gid=0
    # A direct root install must still produce a non-root image. UID/GID 1000
    # are the portable Docker defaults; sudo preserves the invoking identity.
    if [ "$host_uid" = "0" ]; then
        host_uid=1000
    fi
    if [ "$host_gid" = "0" ]; then
        host_gid=1000
    fi
    set_env_number OCTOAGENT_UID "$host_uid"
    set_env_number OCTOAGENT_GID "$host_gid"
    if [ -S /var/run/docker.sock ]; then
        if [ "$(uname -s)" = "Darwin" ]; then
            docker_gid="$(stat -f '%g' /var/run/docker.sock)"
        else
            docker_gid="$(stat -c '%g' /var/run/docker.sock)"
        fi
    fi
    set_env_number OCTOAGENT_DOCKER_GID "$docker_gid"
    if [ "$(id -u)" = "0" ]; then
        chown -R "$host_uid:$host_gid" logs backend/runtime runtime/config runtime/cache runtime/langgraph runtime/logs runtime/secrets runtime/system_tools skills/custom workspace tmp
    fi
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
configure_container_identity

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
