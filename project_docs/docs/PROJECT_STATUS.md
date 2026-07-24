# OctoAgent Project Status

**Last verified:** 2026-07-24
**Version:** 20260724.1.0

## Product truth

OctoAgent has one agent runtime and one capability boundary:

- **Agent Runtime (LangGraph)** owns the model loop, thread/run lifecycle,
  checkpoint persistence, streaming, and post-run hooks.
- **Harness** owns live capability discovery, permission filtering, tool
  binding and dispatch, artifacts, and Markdown memory with pgvector recall.
- **FastAPI** exposes control/configuration APIs from the same `app-server`
  process as the Agent Runtime. It is not a second execution engine.
- **system-executor** is the only root boundary. It is an authenticated Docker
  adapter used by Harness in `system` permission mode.
- **PostgreSQL + pgvector** is the authoritative durable store for LangGraph
  state, projects, and the derived memory index.

Tools Hub, Brain Core, Query Engine, Task Workspace, Local Work Bus, Redis,
the mock System Execution control plane, and the independent execution worker
are not part of the active architecture.

## Production services

`compose.yaml` defines five services:

| Service | Identity | Responsibility |
| --- | --- | --- |
| `nginx` | unprivileged image user | Single public HTTP entrypoint |
| `frontend` | `node` | Next.js workspace UI |
| `app-server` | uid/gid `1000:1000` | FastAPI, LangGraph, Harness |
| `system-executor` | `0:0` | Authenticated host/root command adapter |
| `postgres` | PostgreSQL image user | Checkpoints, projects, pgvector memory |

The authoritative deployment environment is `.env.docker`. Runtime
configuration is mounted at `/app/runtime/config/config.yaml`; user workspaces
are mounted at `/app/workspace`.

## Execution flow

1. The WebUI submits messages and the selected model/permission context.
2. LangGraph resolves the project/thread context and enters the model loop.
3. Harness scans enabled built-ins, skills, plugins, and MCP servers.
4. Harness filters tools by `directory` or `system` permission mode.
5. The model chooses whether and how to call an exposed tool.
6. Harness dispatches to its container, MCP/browser, or root-executor adapter.
7. Tool results return to the model loop; LangGraph streams and checkpoints
   the final state.
8. The post-run memory hook writes raw and compacted Markdown and updates the
   pgvector index. Markdown remains the source of truth.

The chat-bar permission selector changes the context submitted with the next
run. `directory` excludes `host_shell`; `system` exposes it through the
authenticated root executor.

## Verified production baseline

- Five Compose services healthy on Linux ARM64 Docker Engine.
- PostgreSQL restart persistence retained 25 threads and 2594 checkpoints.
- Live module CRUD closure passed for models, skills, MCP, agents, projects,
  and plugins.
- Native LangGraph local-model run returned `FINAL_RUNTIME_OK`.
- Harness inventory: MCP 5/5, skills 32/32, plugins 16/16, built-ins 102.
- Memory: 117 Markdown sources, 117 pgvector rows, zero pending.
- Root execution: unauthenticated requests rejected; authenticated
  `host_shell` ran as uid 0, reached Docker Engine, and reached the Internet.
- Backend: 507 tests, Ruff, and compileall passed before the final executor
  boundary test was added.
- Frontend: Next.js production build and TypeScript checks passed.
- Clean Docker installation lifecycle passed health, restart, persistence,
  upgrade, stop/start, and removal.

## Release verification

Run these gates before release:

```bash
cd backend
.venv/bin/python -m compileall -q src scripts
.venv/bin/python -m ruff check src scripts tests
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_release_readiness_contract_smoke.py
.venv/bin/python -m pytest -q tests/system_executor/test_app.py

cd ../frontend
pnpm lint
pnpm typecheck
pnpm build

cd ..
python3 scripts/verify-module-lifecycles.py
```

Historical reports under `project_docs/docs/` describe earlier architectures
and are not runtime authority. Use this file, `README.md`, `compose.yaml`, and
the live `/api/runtime/doctor` and `/api/harness` responses for current truth.
