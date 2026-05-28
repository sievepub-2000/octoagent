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
| `postgres` | Packaged PostgreSQL sidecar for DB/MCP checks | internal `5432` |
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

- `config.yaml`
- `.env.docker`
- `logs/`
- `runtime/cache/`
- `runtime/logs/`
- `runtime/system_tools/`
- `workspace/`

`.env.docker` is ignored by git. The installer replaces the placeholder `BETTER_AUTH_SECRET` with a random 48-byte secret on first run.

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
```

Edit `config.yaml` for model cards and agent behavior. The container profile mounts it read-only into `/app/config.yaml`.

## MCP And System Tools

The Docker profile configures all packaged MCP servers with environment-variable paths so the same `extensions_config.json` works on a host checkout and inside containers. The default packaged sidecars make Redis and PostgreSQL MCP smoke checks available without extra host services.

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

The Tools Hub is available at:

```text
http://127.0.0.1:19800/workspace/config/tools
```
