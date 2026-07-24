# Docker Installation And Deployment

Docker Compose is the only supported OctoAgent production distribution. Host
Python, Node.js, pnpm, nginx, PostgreSQL, and Redis are not required.

## Runtime Topology

`compose.yaml` starts five services:

| Service | Purpose | Default exposure |
| --- | --- | --- |
| `nginx` | Public WebUI and API ingress | `0.0.0.0:19800` |
| `frontend` | Production Next.js WebUI | `127.0.0.1:19806` |
| `app-server` | FastAPI, LangGraph agent runtime, Harness, memory | `127.0.0.1:19802` |
| `system-executor` | Authenticated host/system execution adapter | internal `19808` |
| `postgres` | Checkpoints, threads, projects, traces, pgvector memory | internal `5432` |

The `app-server` is the single model-facing backend. Harness dynamically scans
and dispatches built-in tools, MCP servers, skills, plugins, hooks, container
execution, host execution, and browser adapters. FastAPI control endpoints and
LangGraph share this process; Redis and separate Gateway, LangGraph, and Tools
Hub services are not part of the current topology.

## Prerequisites

- Linux: Docker Engine 24+ and Compose v2.
- Windows 11: Docker Desktop using Linux containers.
- macOS: Docker Desktop, OrbStack, or a compatible Docker Engine.
- Git is needed only when the installer must clone the repository.

## One-Command Installation

Linux and macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.sh | bash
```

Windows PowerShell:

```powershell
iwr https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.ps1 -UseBasicParsing | iex
```

From an existing checkout:

```bash
git clone https://github.com/sievepub-2000/octoagent.git
cd octoagent
./scripts/install-docker.sh --prefix "$PWD"
```

The installer creates ignored runtime state, generates authentication secrets,
builds the images, starts the stack, and waits for:

```text
http://127.0.0.1:19800/health
```

## Authoritative Runtime State

| Data | Host path / Docker volume | Container path |
| --- | --- | --- |
| Model and agent config | `runtime/config/config.yaml` | `/app/runtime/config/config.yaml` |
| Harness extensions | `runtime/config/extensions_config.json` | `/app/runtime/config/extensions_config.json` |
| Model secrets | `runtime/secrets/models.env` | `/app/runtime/secrets/models.env` |
| Raw and compact memory | `runtime/memory/*.md` | `/app/runtime/memory` |
| Checkpoints, threads, vectors | `octoagent_postgres-data` | `/var/lib/postgresql/data` |
| Workspace and project state | `workspace/` | `/app/workspace` |
| LangGraph local runtime index | `runtime/langgraph/` | `/app/backend/.langgraph_api` |

Markdown is the durable human-readable memory source. Harness indexes it into
PostgreSQL pgvector during initialization and after writes. Legacy JSON and
DuckDB stores are not live sources and are not scanned during startup.

## Daily Operations

Start or upgrade after pulling code:

```bash
git pull --ff-only
docker compose --env-file .env.docker -f compose.yaml up -d --build --remove-orphans
```

Check health:

```bash
docker compose --env-file .env.docker -f compose.yaml ps
curl -fsS http://127.0.0.1:19800/health
curl -fsS http://127.0.0.1:19800/api/runtime/doctor
curl -fsS http://127.0.0.1:19800/api/harness
```

View logs:

```bash
docker compose --env-file .env.docker -f compose.yaml logs -f \
  nginx frontend app-server system-executor postgres
```

Restart without deleting data:

```bash
docker compose --env-file .env.docker -f compose.yaml restart
```

Stop while preserving data:

```bash
docker compose --env-file .env.docker -f compose.yaml down
```

Remove containers and the PostgreSQL volume:

```bash
docker compose --env-file .env.docker -f compose.yaml down -v
```

The final command permanently deletes database-backed conversations, projects,
checkpoints, traces, and vector memory. Markdown memory and workspace bind
mounts remain until their host directories are explicitly removed.

## Permissions

The normal `app-server` runs as the non-root `octoagent` user. It has read/write
access only to the declared bind mounts and full outbound Internet access.

`system-executor` runs as root, is reachable only on the Compose network,
requires the generated bearer token, and alone mounts `/var/run/docker.sock`.
The chat permission selector enforces:

- `container`: container/directory tools only; host tools are absent.
- `system`: adds host shell, filesystem, network, process, and Docker tools.

System-mode commands are traced. Never publish port `19808` or share
`OCTOAGENT_SYSTEM_EXECUTOR_TOKEN`.

## Configuration And Network

Edit `.env.docker` for ports, provider keys, build mirrors, and proxy settings.
Edit `runtime/config/config.yaml` for model cards. Harness-managed MCP, skill,
plugin, and hook configuration lives in
`runtime/config/extensions_config.json`.

Internal service names `app-server`, `postgres`, `system-executor`, and
`host.docker.internal` must bypass any outbound proxy. A host proxy bound to
`127.0.0.1` must be addressed as `host.docker.internal` from containers.

Common image mirror overrides:

```dotenv
OCTOAGENT_POSTGRES_IMAGE=mirror.example.com/pgvector/pgvector:pg16-bookworm
OCTOAGENT_NGINX_IMAGE=mirror.example.com/library/nginx:1.27-alpine
OCTOAGENT_PYTHON_BASE_IMAGE=mirror.example.com/library/python:3.12-slim
OCTOAGENT_NODE_RUNTIME_IMAGE=mirror.example.com/library/node:22-bookworm-slim
OCTOAGENT_NODE_FRONTEND_IMAGE=mirror.example.com/library/node:22-alpine
OCTOAGENT_DOCKER_CLI_IMAGE=mirror.example.com/library/docker:cli
OCTOAGENT_UV_IMAGE=mirror.example.com/astral-sh/uv:0.7.20
OCTOAGENT_NPM_REGISTRY=https://registry.npmmirror.com
```

## Migration And Backup

Before an upgrade, back up both state surfaces:

```bash
docker exec octoagent-postgres-1 pg_dump -U octoagent -Fc octoagent \
  > octoagent-postgres.dump
tar -czf octoagent-runtime-state.tgz runtime/config runtime/memory \
  runtime/secrets runtime/langgraph workspace
```

Restore PostgreSQL into `octoagent_postgres-data` and restore the bind-mounted
directories before starting the stack. Verify an existing thread and memory
search both before and after a full restart.

## Verification

The acceptance baseline is:

```bash
curl -fsS http://127.0.0.1:19800/health
curl -fsS http://127.0.0.1:19800/api/runtime/doctor
curl -fsS http://127.0.0.1:19800/api/harness
docker compose --env-file .env.docker -f compose.yaml config --quiet
```

Then verify:

1. All five services are healthy.
2. A model run replies and a self-check calls
   `inspect_octoagent_runtime`/`list_capabilities` without web search.
3. Thread and project create/read/update/delete lifecycles close cleanly.
4. Markdown memory remains searchable after `app-server` restart.
5. Container mode excludes `host_shell`; system mode exposes it and can access
   the host, Docker socket, and Internet.
6. The WebUI Harness counts match `/api/harness`.

The Harness management surface is available in Settings → Harness and at:

```text
http://127.0.0.1:19800/workspace/config/tools
```
