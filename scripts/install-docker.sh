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
    # Never let a fixed COMPOSE_PROJECT_NAME in a copied env file make an
    # isolated install reuse another checkout's containers or volumes.
    local project_name="${OCTOAGENT_COMPOSE_PROJECT_NAME:-$(basename "$PREFIX")}"
    docker compose --project-name "$project_name" --env-file .env.docker -f compose.yaml "$@"
}

configure_build_proxy_env() {
    # BuildKit does not inherit the Docker daemon's systemd proxy. Forward
    # explicit shell values first, then recover daemon proxy values on Linux;
    # keep these build-only variables separate from runtime HTTP_PROXY.
    export OCTOAGENT_BUILD_HTTP_PROXY="${OCTOAGENT_BUILD_HTTP_PROXY:-${HTTP_PROXY:-}}"
    export OCTOAGENT_BUILD_HTTPS_PROXY="${OCTOAGENT_BUILD_HTTPS_PROXY:-${HTTPS_PROXY:-}}"
    export OCTOAGENT_BUILD_NO_PROXY="${OCTOAGENT_BUILD_NO_PROXY:-${NO_PROXY:-}}"
    export OCTOAGENT_BUILD_NETWORK="${OCTOAGENT_BUILD_NETWORK:-default}"
    if command -v systemctl >/dev/null 2>&1; then
        local daemon_env token
        daemon_env="$(systemctl show docker --property=Environment --value 2>/dev/null || true)"
        for token in $daemon_env; do
            case "$token" in
                HTTP_PROXY=*) [ -n "$OCTOAGENT_BUILD_HTTP_PROXY" ] || export OCTOAGENT_BUILD_HTTP_PROXY="${token#HTTP_PROXY=}" ;;
                HTTPS_PROXY=*) [ -n "$OCTOAGENT_BUILD_HTTPS_PROXY" ] || export OCTOAGENT_BUILD_HTTPS_PROXY="${token#HTTPS_PROXY=}" ;;
                NO_PROXY=*) [ -n "$OCTOAGENT_BUILD_NO_PROXY" ] || export OCTOAGENT_BUILD_NO_PROXY="${token#NO_PROXY=}" ;;
            esac
        done
    fi
    if [ "$OCTOAGENT_BUILD_NETWORK" = "default" ] && [ -n "$OCTOAGENT_BUILD_HTTP_PROXY" ] && command -v systemctl >/dev/null 2>&1; then
        # Linux daemon proxies commonly bind only to 127.0.0.1; host BuildKit
        # networking is the only way for the build namespace to reach them.
        export OCTOAGENT_BUILD_NETWORK=host
    fi
}

env_value() {
    local key="$1"
    grep -E "^${key}=" .env.docker | tail -1 | cut -d= -f2-
}

build_platform() {
    local configured arch
    configured="$(env_value OCTOAGENT_BUILD_PLATFORM)"
    if [ -n "$configured" ]; then
        printf '%s' "$configured"
        return
    fi
    arch="$(docker info --format '{{.Architecture}}' 2>/dev/null || true)"
    case "$arch" in
        aarch64|arm64) printf '%s' "linux/arm64" ;;
        amd64|x86_64) printf '%s' "linux/amd64" ;;
        *) printf '%s' "" ;;
    esac
}

ensure_build_base_images() {
    local spec key default image platform
    platform="$(build_platform)"
    local -a specs=(
        "OCTOAGENT_PYTHON_BASE_IMAGE|python:3.12-slim"
        "OCTOAGENT_NODE_RUNTIME_IMAGE|node:22-bookworm-slim"
        "OCTOAGENT_DOCKER_CLI_IMAGE|docker:cli"
        "OCTOAGENT_UV_IMAGE|ghcr.io/astral-sh/uv:0.7.20"
        "OCTOAGENT_NODE_FRONTEND_IMAGE|node:22-alpine"
    )
    for spec in "${specs[@]}"; do
        key="${spec%%|*}"
        default="${spec#*|}"
        image="$(env_value "$key")"
        image="${image:-$default}"
        if docker image inspect "$image" >/dev/null 2>&1; then
            continue
        fi
        echo "Pulling build base image: $image"
        if [ -n "$platform" ]; then
            pull_cmd=(docker pull --platform "$platform" "$image")
        else
            pull_cmd=(docker pull "$image")
        fi
        if ! "${pull_cmd[@]}"; then
            cat >&2 <<EOF
Failed to pull build base image: $image
Configure $key in .env.docker to a reachable registry mirror, or fix the
Docker daemon proxy before retrying. The installer will not continue with a
partially pullable build.
EOF
            return 1
        fi
    done
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
    if grep -q 'replace-with-a-long-random-system-executor-token' .env.docker; then
        system_executor_secret="$(random_secret)"
        if sed --version >/dev/null 2>&1; then
            sed -i "s#replace-with-a-long-random-system-executor-token#$system_executor_secret#" .env.docker
        else
            sed -i '' "s#replace-with-a-long-random-system-executor-token#$system_executor_secret#" .env.docker
        fi
    elif ! grep -q '^OCTOAGENT_SYSTEM_EXECUTOR_TOKEN=' .env.docker; then
        printf '\nOCTOAGENT_SYSTEM_EXECUTOR_TOKEN=%s\n' "$(random_secret)" >> .env.docker
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
    if grep -q '^OCTOAGENT_HOST_REPO_ROOT=' .env.docker; then
        if sed --version >/dev/null 2>&1; then
            sed -i "s#^OCTOAGENT_HOST_REPO_ROOT=.*#OCTOAGENT_HOST_REPO_ROOT=$PREFIX#" .env.docker
        else
            sed -i '' "s#^OCTOAGENT_HOST_REPO_ROOT=.*#OCTOAGENT_HOST_REPO_ROOT=$PREFIX#" .env.docker
        fi
    else
        printf '\nOCTOAGENT_HOST_REPO_ROOT=%s\n' "$PREFIX" >> .env.docker
    fi
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
configure_build_proxy_env

if [ "$BUILD" = "1" ]; then
    ensure_build_base_images
fi

if [ "$PULL" = "1" ]; then
    compose pull
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
