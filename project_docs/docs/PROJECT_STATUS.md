# OctoAgent Project Status

**Last Updated**: 2026-04-27

## What The Project Is

OctoAgent is a task-centric multi-agent platform built around the active topology below:

- Next.js workspace UI
- FastAPI gateway and projection layer
- LangGraph runtime as the only active execution backend

The repository still contains transitional and operator-oriented surfaces, but the current product truth is no longer “dual runtime”. Older provider labels are compatibility aliases only.

## Current Verified Truth

- Backend top-level module inventory: **45** directories under `backend/src`
- Gateway router groups: **38** registered groups (**41** router files)
- Active execution provider: **`langgraph`**
- Primary workflow truth source: **`task_workspaces` + `workflow_core` projections**
- Main workflow lifecycle endpoints: **`/api/task-workspaces/{task_id}/compile|run|pause|resume|terminate`**
- Main workflow runtime read model: **`/api/task-workspaces/{task_id}/studio-runtime`**
- Public external runtime projection: **`/api/runtime/workflows/*`**
- Unified local entrypoint: **`http://127.0.0.1:19880`**
- Built-in account store: **`workspace/runtime/octoagent_users.db`** with email-code registration, trusted-device sessions, and tenant binding through `/api/auth/*`
- Repo-owned workspace default now takes precedence when explicit setup state is absent and `workspace/` already exists

## Runtime Surface Truth

### Product surface

- The workflow pages in the frontend use the `task_workspaces` contract for compile/run/pause/resume/terminate.
- Studio runtime data shown in the UI is read through the task-workspace projection endpoints, not through the standalone `/api/studio/*` builder router.
- `agent_core` now owns most task-level and agent-level lifecycle transitions that used to leak through router-local or workflow-local status writes.

### Transitional surface

- The historical `studio_runtime` sandbox implementation remains in the repository, but `/api/studio/*` is no longer registered in the default gateway surface.
- It is not the workflow product truth used by `TaskWorkspaceBoard`.
- The near-term rule is to keep task-workspace lifecycle and public runtime projections as the only default workflow-facing surfaces.

## Landed Capabilities

### Runtime and orchestration

- `agent_runtime` normalizes older provider aliases to `langgraph` and routes real execution through the LangGraph provider.
- `workflow_core` owns studio/public runtime projections, builder preview/history, and artifact/runtime summaries.
- `task_workspaces` remains the durable execution source for task workflow state, cards, checkpoints, and runtime metadata.
- `agent_core` owns lifecycle/event/status transitions, handoff session compatibility, and task/agent execution facades.

### Operator and integration surfaces

- Capability binding contract endpoint: `/api/capabilities/binding-contract` exposes bindable targets, dispatch contracts, blockers, and audit metadata across skills, plugins, MCP servers, hooks, channels, and compatibility items.
- Public runtime APIs under `/api/runtime/workflows/*` are landed.
- System update APIs are available under `/api/system/update/*`.
- System memory read APIs are available for search/list/stats.
- Hook and capability service boundaries are real and already wired into runtime flows, but still need deeper product closure.

### Frontend surfaces

- Workflow overview and workflow detail pages are live and use task-workspace APIs.
- Workflow result cards support markdown, attachments, and failure analysis.
- Setup, models, MCP, plugins, channels, memory, and evolution configuration surfaces are present in the workspace UI.

## Module Maturity Summary

### Stable enough for continued integration

- gateway
- workflow_core
- task_workspaces
- agent_core
- agent_runtime
- agents
- tools / tools_registry
- browser_runtime
- query_engine
- config / bootstrap / models

### Active closure track

- hook_core
- capability_core
- studio runtime product boundary
- workflow builder / runtime contract alignment
- repository hygiene around workspace runtime state

### Present but still operator-substrate oriented

- distributed_execution
- multi_tenant
- monitoring
- reflection
- self_evolution

These modules are real, but they are not equally complete.

- `distributed_execution`, `monitoring`, `reflection`, and `self_evolution` now have a minimal operator panel inside the system settings surface, directly backed by their existing APIs.
- `multi_tenant` remains API-first and contract-oriented; it still lacks auth binding, durable policy state, and an admin UI.
- `distributed_execution` still lacks a real remote-dispatch control plane.
- `monitoring` still lacks alert policy and richer workflow/runtime visualization.
- `reflection` and `self_evolution` now have WebUI visibility, but they are still governance/operator substrates rather than autonomous product features.

## Repository Hygiene Truth

- `workspace/runtime/*`, `workspace/workflow/task/*`, and `workspace/env/setup.json` are local runtime state, not source code.
- They should not remain tracked in git.
- CI should fail if these runtime-state files re-enter version control.

## Recommended Read Order

1. `README.md`
2. `project_docs/README.md`
3. `project_docs/docs/PROJECT_STATUS.md`
4. `project_docs/docs/PROJECT_PROGRESS.md`
5. `project_docs/docs/P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md`
6. `project_docs/docs/P1_P5_COMPLETION_AND_FULL_CODE_ASSESSMENT_REPORT.md`
7. `project_docs/docs/ARCHITECTURE.md`
8. `project_docs/backend/README.md`

## Boundary Rules

- `config.example.yaml` remains the tracked baseline template.
- Local `config.yaml`, runtime stores, task artifacts, and setup snapshots remain deployment-local state.
- Historical numbered stage reports were consolidated during P0 cleanup; use Git history for forensic review only.
- Claims about runtime behavior should be anchored to the active router/service/frontend code paths, not to old transition narratives.
