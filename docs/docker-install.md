# Docker Installation And Deployment

OctoAgent's default deployment path is Docker Compose. The same profile is used on Linux, Windows, and macOS so operators do not need to install Python, Node.js, pnpm, nginx, PostgreSQL, or Redis on the host.

## What The Packaged Profile Runs

`compose.yaml` starts these containers:

| Service | Purpose | Default port |
| --- | --- | --- |
| `nginx` | Single public entrypoint for WebUI and API | `19800` |
| `frontend` | Production Next.js WebUI | internal `19806` |
| `gateway` | FastAPI gateway and REST APIs | localhost `19802` |
| `langgraph` | Agent runtime | localhost `19804` |
| `postgres` | Packaged PostgreSQL for conversations, checkpoints, and DB/MCP checks | internal `5432` |
| `redis` | Packaged Redis sidecar for Redis MCP checks | internal `6379` |

The backend image also installs the reproducible MCP npm packages from `runtime/tools/mcp/package-lock.json`; it does not rely on runtime `npx` downloads.

## Prerequisites

Install Docker with Compose v2:

- Linux: Docker Engine 24+ with the Compose plugin.
- Windows: Docker Desktop with Linux containers enabled.
- macOS: Docker Desktop, OrbStack, or another Docker-compatible engine.

Git is required only when you run the installer from a URL and need it to clone the repository.

## One-Command Install

Linux and macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.sh | bash
```

Install to a custom directory:

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.sh | bash -s -- --prefix "$HOME/octoagent"
```

Windows PowerShell:

```powershell
iwr https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.ps1 -UseBasicParsing | iex
```

Windows with a custom checkout path:

```powershell
$env:OCTOAGENT_HOME="$HOME\octoagent"
iwr https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.ps1 -UseBasicParsing | iex
```

After the health check passes, open:

```text
http://127.0.0.1:19800
```

## Install From An Existing Checkout

```bash
git clone https://github.com/sievepub-2000/octoagent.git
cd octoagent
./scripts/install-docker.sh --prefix "$PWD"
```

The installer creates local runtime files if they do not exist:

- `runtime/config/config.yaml`
- `.env.docker`
- `logs/`
- `runtime/cache/`
- `runtime/logs/`
- `runtime/langgraph/`
- `runtime/secrets/`
- `runtime/system_tools/`
- `skills/custom/`
- `workspace/`

`.env.docker` is ignored by git. On first run the installer replaces the
placeholder `BETTER_AUTH_SECRET` with a random 48-byte secret and the packaged
PostgreSQL placeholder with a URL-safe random 24-byte hex password.

## Daily Operations

Start or update after pulling new code:

```bash
docker compose --env-file .env.docker -f compose.yaml up -d --build --remove-orphans
```

Check service status:

```bash
docker compose --env-file .env.docker -f compose.yaml ps
curl -fsS http://127.0.0.1:19800/health
```

View logs:

```bash
docker compose --env-file .env.docker -f compose.yaml logs -f nginx gateway langgraph frontend
```

Stop:

```bash
docker compose --env-file .env.docker -f compose.yaml down
```

Remove packaged database volumes as well:

```bash
docker compose --env-file .env.docker -f compose.yaml down -v
```

## Base Image Mirrors

If Docker Hub or CloudFront is slow or blocked, keep `compose.yaml` unchanged and override image names in `.env.docker`:

```dotenv
OCTOAGENT_POSTGRES_IMAGE=mirror.example.com/library/postgres:16-alpine
OCTOAGENT_REDIS_IMAGE=mirror.example.com/library/redis:7-alpine
OCTOAGENT_NGINX_IMAGE=mirror.example.com/library/nginx:1.27-alpine
OCTOAGENT_PYTHON_BASE_IMAGE=mirror.example.com/library/python:3.12-slim
OCTOAGENT_NODE_RUNTIME_IMAGE=mirror.example.com/library/node:22-bookworm-slim
OCTOAGENT_NODE_FRONTEND_IMAGE=mirror.example.com/library/node:22-alpine
```

This is useful for China-region networks, enterprise registries, and offline registry mirrors.

## Configuration

Edit `.env.docker` for ports, provider keys, and runtime tokens. Common values:

```dotenv
OCTO_NGINX_PORT=19800
OCTOAGENT_MODEL_AUTH_OPENROUTER=sk-or-v1-...
TAVILY_API_KEY=...
POSTGRES_PASSWORD=change-this-before-shared-use

# OpenRouter attribution and usage accounting opt-in.
OCTOAGENT_OPENROUTER_APP_URL=https://github.com/sievepub-2000/octoagent
OCTOAGENT_OPENROUTER_APP_TITLE=OctoAgent
OCTOAGENT_OPENROUTER_USAGE_INCLUDE=true
```

Edit `runtime/config/config.yaml` for model cards and agent behavior. The container profile
mounts the containing directory read/write into `/app/runtime/config` because model and channel settings
use atomic file replacement when persisted by the WebUI. `runtime/config/extensions_config.json` is also read/write so MCP,
skills, hooks, and plugin lifecycle changes survive a restart.

If the host needs an outbound proxy to reach model or search providers, copy
its `HTTP_PROXY`, `HTTPS_PROXY`, lowercase variants, and `NO_PROXY` values into
`.env.docker`. A proxy listening on host `127.0.0.1` must be written as
`host.docker.internal` from inside the containers. Keep `gateway`, `langgraph`, `postgres`, `redis`, and
`host.docker.internal` in `NO_PROXY`. Avoid defining both `GOOGLE_API_KEY` and
`GEMINI_API_KEY`; Google GenAI warns when both are present and chooses one by
SDK precedence.

The Compose profile explicitly points the checkpointer at its PostgreSQL
service through `OCTOAGENT_CHECKPOINTER_DSN`. This runtime override prevents a
preserved host configuration from accidentally using a container-local SQLite
file or a host-only `127.0.0.1` PostgreSQL address; it does not rewrite the
operator's YAML file.

Backend containers run as the invoking user's UID/GID on Linux/macOS. The
install script records these values in `.env.docker`, preventing root-owned
files in bind-mounted configuration and workspace directories. When invoked
through `sudo`, the original user's UID/GID is retained; a direct root install
uses the non-root container default `1000:1000` and transfers only mutable bind
mounts to that identity.

Built-in skills are packaged in the backend image. User-installed and
user-created skills are stored separately in the `skills/custom/` bind mount,
so image rebuilds and upgrades do not remove them.

## MCP And System Tools

The Docker profile resolves the packaged filesystem, PostgreSQL, OpenAPI,
Docker Compose, Redis, and Docker MCP commands through runtime environment
overrides. Existing descriptions, enabled state, permission scopes, smoke
tests, headers, and credentials remain in the single writable
`runtime/config/extensions_config.json`; host-only executable paths and localhost sidecar
addresses are mapped in memory to their container equivalents. The default
packaged sidecars make Redis and PostgreSQL MCP smoke checks available without
extra host services.

Docker MCP mounts `/var/run/docker.sock` into the backend containers. On hardened Docker Desktop installations, you may need to enable Docker socket access or run the containers from WSL2/macOS where the socket is available.

## Packaging A Release Bundle

From a clean checkout:

```bash
./scripts/package-docker.sh
```

The script writes `dist/octoagent-docker-<version>.tar.gz` plus a SHA-256 file. The archive contains the source tree and Docker installation assets; extract it and run `./scripts/install-docker.sh --prefix "$PWD"` from the extracted directory.

## Verification Checklist

A healthy Docker deployment should pass:

```bash
curl -fsS http://127.0.0.1:19800/health
curl -fsS http://127.0.0.1:19800/api/tools/registry
curl -fsS http://127.0.0.1:19800/api/mcp/smoke
```

Run the isolated lifecycle verifier from the checkout to validate create,
read, update, archive/confirmed delete, and post-delete visibility for the configurable
modules:

```bash
python3 scripts/verify-module-lifecycles.py \
  --base-url http://127.0.0.1:19800 \
  --env-file .env.docker
```

Add `--include-channel` only on a clean installation; it temporarily configures
one previously unconfigured channel and then clears it.

The Tools Hub is available at:

```text
http://127.0.0.1:19800/workspace/config/tools
```
