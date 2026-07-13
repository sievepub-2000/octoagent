# OctoAgent architecture

Last updated: 2026-07-13

## Runtime topology

```text
Browser :19800 (nginx)
  ├─ Next.js WebUI :19806
  ├─ FastAPI gateway :19802
  └─ LangGraph runtime :19804
       ├─ lead agent and middleware
       ├─ tools / MCP / browser execution
       └─ checkpoint and memory stores
```

## User-facing domain

The primary hierarchy is `Project -> Task -> Run`.

- A **Project** is a durable context stored independently from workflow runs. It owns a validated root directory, Git metadata, instructions, defaults, pinned files, and project memory.
- A **Task** is a conversational LangGraph thread associated with an optional `project_id`.
- A **Run** is an execution within a task. Run activity and artifacts appear in the right context panel.
- Workflow and subagent orchestration are runtime implementation details, not top-level user objects.

## WebUI layout

- Left: projects and their recent tasks.
- Center: chat, execution controls, messages, and prompt.
- Right: Activity, Files, and System tabs.
- Advanced administration: Settings panel.

The frontend uses flat shadcn-style surfaces. Legacy workflow inspector, task-workspace canvas, and global status strip are removed from the public workspace.

## Key APIs

- `GET/POST /api/projects`
- `GET/PUT/DELETE /api/projects/{project_id}`
- `GET/PUT /api/projects/{project_id}/memory`
- `GET /api/system/overview`
- LangGraph thread and run APIs under the runtime gateway.

## Release gates

Backend changes require Ruff, compile, and focused pytest coverage. Frontend changes require zero-warning ESLint, TypeScript, production build, and browser smoke verification through nginx.
