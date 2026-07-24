# OctoAgent Domain Context

OctoAgent is a self-hosted agent system with two public Modules. Agent Runtime
owns model turns and native LangGraph thread/run/checkpoint/stream state.
Harness owns every capability and execution concern. Projects are lightweight
PostgreSQL metadata attached to those native threads; OctoAgent does not keep a
second Task/Run/Event state machine. The Docker-only deployment keeps the root
System Executor physically isolated from the unprivileged application process.

## Core terms

- **Agent Runtime** is the deep Interface for model execution and native
  LangGraph thread, run, checkpoint, and stream state.
- **Project** is PostgreSQL-backed organization and permission metadata. A
  conversation is a LangGraph thread and an execution is a LangGraph run.
- **Harness** is the deep Interface for dynamic capability discovery,
  permission dispatch, execution adapters, tracing, artifacts, and memory.
- **Capability Registry** is a private Harness dictionary rebuilt from live
  sources. It is not a Module, database, or separate UI.
- **Managed Tool** is an operator-approved standalone tool owned by exactly one
  directory at `runtime/system_tools/<name>/` and exactly one `manifest.json`.
- **Bundled Skill** is versioned application capability under `skills/public`;
  its application dependencies belong to the locked backend environment.
- **Tool artifact** is generated output under a managed tool's `artifacts/`
  directory. Source, dependencies, manifests, cache, and logs are separate.
- **User artifact** is a deliverable under a conversation `outputs/` directory;
  it is presented in the Files panel and is never removed by automatic
  retention.
- **Memory Markdown** is the durable source of truth; pgvector is a derived,
  rebuildable retrieval index initialized by Harness.

## Invariants

1. Search Harness before installing anything; try existing suitable tools in
   least-privilege order.
2. GitHub fallback requires a pinned source, user approval, managed directory,
   smoke verification, manifest registration, and automatic Harness refresh.
3. System permission is required for install and delete. Directory/approval
   modes cannot receive those tools. Delete is manifest-owned and path-guarded.
4. Automatic cleanup may touch only policy-owned disposable roots. It cannot
   remove user outputs, memories, configuration, secrets, source, tool
   manifests, entrypoints, or dependency environments.
5. Full audits verify the live runtime source, duplicate data sources,
   ownership, permission enforcement, CRUD closure, restart persistence, clean
   install, and cross-platform syntax; source scans alone are insufficient.
