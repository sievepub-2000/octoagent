# OctoAgent Tools Catalog

Canonical list of every capability surfaced through the `/api/skills`,
`/api/mcp/config`, `/api/channels/`, `/api/plugins/registry`, and `/api/hooks`
endpoints. Keep this in sync with the Settings → Tools Hub view
(`frontend/src/app/workspace/config/tools/page.tsx`).

## Categories

| Category | Source API | Frontend Panel | Notes |
|----------|------------|----------------|-------|
| Skills   | `GET /api/skills` | Settings → Skills | Workflow recipes loaded from `skills/` |
| MCP Servers | `GET /api/mcp/config` | Settings → MCP | Registered via `POST /api/mcp/servers` |
| Channels | `GET /api/channels/` | Settings → Channels | Chat adapters (slack, lark, …) |
| Plugins  | `GET /api/plugins/registry` | Settings → Plugins | Runtime plugin registry |
| Hooks    | `GET /api/hooks` | (auto) | Lifecycle triggers |

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
