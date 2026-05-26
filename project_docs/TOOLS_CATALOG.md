# OctoAgent Tools Catalog

Canonical list of every capability surfaced through the `/api/skills`,
`/api/mcp/config`, `/api/channels/`, `/api/plugins/registry`, `/api/agents`,
and `/api/hooks` endpoints. Keep this in sync with the Settings → Tools Hub view
(`frontend/src/app/workspace/config/tools/page.tsx`).

## Categories

| Category | Source API | Frontend Panel | Notes |
|----------|------------|----------------|-------|
| Skills   | `GET /api/skills` | Settings → Skills | Workflow recipes loaded from `skills/` |
| MCP Servers | `GET /api/mcp/config` | Settings → MCP | Registered via `POST /api/mcp/servers` |
| Channels | `GET /api/channels/` | Settings → Channels | Chat adapters (slack, lark, …) |
| Plugins  | `GET /api/plugins/registry` | Settings → Plugins | Runtime plugin registry |
| Agents | `GET /api/agents` | Workspace → Agents | Custom agents plus immutable skill-exported templates |
| Hooks    | `GET /api/hooks` | (auto) | Lifecycle triggers |

## MCP readiness notes

MCP server cards are backed by `POST /api/mcp/servers` and
`DELETE /api/mcp/servers/{name}` for single-server mutations. Runtime startup
fails closed for enabled MCP entries with unresolved environment variables.
For example, Tavily requires `TAVILY_API_KEY`; when absent, the API
returns `missing_env: ["TAVILY_API_KEY"]` and the server is skipped rather
than started with an empty secret.

## Agent catalog notes

`GET /api/agents` is source-aware:

- `source: "custom"` entries are editable, deletable, and chat-enabled.
- `source: "template"` entries come from installed skills and are immutable.
   The WebUI routes them into the new-agent form so users create a real custom
   agent copy before chatting or workflow binding.

## System Tool Installation Policy

When a user mentions "system" without a qualifier, agents should interpret it as the OctoAgent agent system/runtime. Use "operating system", "OS", "host", "machine", or "server" for host operating-system work. If an installation or destructive action depends on the distinction, ask a concise clarification before acting.

Tool, package, runtime, and dependency installation requires explicit user confirmation before execution. The confirmation must cover the package/tool list, target tool directory, and whether the change affects the host OS or the OctoAgent runtime.

Installation locations:

- Tool-owned Python packages should default to `runtime/system_tools/<tool_name>/.venv` via `python_package_install` with `target_tool` set.
- Tool artifacts and generated runtime files must stay under `runtime/system_tools/<tool_name>/`.
- The shared backend environment `backend/.venv` may be modified only when the user explicitly confirms that the OctoAgent runtime itself should change.

After every successful tool installation or tool-behavior change, run a real verification command and update this catalog or the owning tool documentation with the path, usage, and verification result.

## Usage contract

All entries exposed to the Tools Hub follow the `ToolEntry` shape:

```ts
interface ToolEntry {
  id: string;         // "skill:<id>" | "mcp:<name>" | "channel:<name>" | "plugin:<id>" | "hook:<name>"
  name: string;       // user-facing label
  category: "skill" | "mcp" | "channel" | "plugin" | "hook";
  description?: string;
  usage?: string;
  enabled?: boolean;
}
```

When adding a new capability:

1. Expose it through the existing router (do not add a new one just for the
   catalog).
2. Add a normaliser branch in `tools/page.tsx::normalizeEntries`.
3. Append an entry here (or a link to the owning doc).
4. Trigger `.github/copilot-instructions.md` regeneration by calling
   `async_refresh_agent_tool_guide()` from the affected router hook.

## Fallback model pool (free-claude-code)

Set `NVIDIA_API_KEY` (or `FREE_CLAUDE_CODE_API_KEY`) and three NVIDIA NIM
models auto-register as fallback:

- `nvidia-llama-3.3-70b`
- `nvidia-deepseek-r1`
- `nvidia-qwen2.5-coder-32b`

See `backend/src/config/free_claude_code_fallback.py`. The injector only runs
when the env var is present and no operator-defined NVIDIA entry exists, so
existing setups stay unchanged.
### FAISS RAG Runtime Tool

- FAISS belongs to the OctoAgent RAG runtime and is imported by backend code, so `faiss-cpu` is installed in `backend/.venv` and tracked in backend dependency manifests.
- Do not install FAISS into a host-level Python environment or a separate tool-local venv.
- If future FAISS index artifacts are materialized outside DuckDB, store those artifacts under `runtime/system_tools/faiss-rag/` while keeping the Python package in `backend/.venv`.
- Verify with `backend/.venv/bin/python -c "import faiss"` and RAG tests before documenting success.
