# OctoAgent Domain Context

OctoAgent is a self-hosted agent runtime whose WebUI, Gateway, LangGraph runtime,
Skills, MCP servers, built-in tools, and operator-installed tools form one
capability system.

## Core terms

- **Tools Hub** is the read model for every usable capability. It is not a
  second installer or database.
- **Managed Tool** is an operator-approved standalone tool owned by exactly one
  directory at `runtime/system_tools/<name>/` and exactly one `manifest.json`.
- **Bundled Skill** is versioned application capability under `skills/public`;
  its application dependencies belong to the locked backend environment.
- **Tool artifact** is generated output under a managed tool's `artifacts/`
  directory. Source, dependencies, manifests, cache, and logs are separate.
- **User artifact** is a deliverable under a conversation `outputs/` directory;
  it is presented in the Files panel and is never removed by automatic
  retention.
- **Harness** is the runtime contract that governs permissions, invocation,
  tracing, verification, artifact ownership, retention, and cleanup.

## Invariants

1. Search Tools Hub before installing anything; try existing suitable tools in
   least-privilege order.
2. GitHub fallback requires a pinned source, user approval, managed directory,
   smoke verification, manifest registration, and automatic Tools Hub refresh.
3. System permission is required for install and delete. Directory/approval
   modes cannot receive those tools. Delete is manifest-owned and path-guarded.
4. Automatic cleanup may touch only policy-owned disposable roots. It cannot
   remove user outputs, memories, configuration, secrets, source, tool
   manifests, entrypoints, or dependency environments.
5. Full audits verify the live runtime source, duplicate data sources,
   ownership, permission enforcement, CRUD closure, restart persistence, clean
   install, and cross-platform syntax; source scans alone are insufficient.
