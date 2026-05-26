---
post_title: "P19 System Linkage And Long Execution Repair"
author1: "GitHub Copilot"
post_slug: "p19-system-linkage-and-long-execution-repair-2026-05-12"
microsoft_alias: "copilot"
featured_image: ""
categories: ["engineering"]
tags: ["octoagent", "agents", "mcp", "workflow", "context-compaction"]
ai_note: "AI-assisted repair and verification report."
summary: "Documents the 2026-05-12 repair pass for real management-page linkage, Firecrawl MCP readiness, right-panel cleanup, and long-running context continuation."
post_date: "2026-05-12"
---

## Scope

This repair pass focused on the runtime management surfaces and long-running
agent execution path:

- right-side Workflow Inspector runtime panel cleanup
- agent catalog linkage to custom agents and installed agent templates
- MCP server add/update/delete wiring and Firecrawl readiness reporting
- plugin configuration UI accuracy
- workflow agent selection after the agent catalog became template-aware
- context-window compaction and continuation for longer autonomous tasks

## System Linkage Results

| Surface | Source API | Mutation API | Result |
| --- | --- | --- | --- |
| Agents | `GET /api/agents` | `POST/PUT/DELETE /api/agents` | Now lists custom agents plus skill-exported templates. Templates are immutable and create custom copies through `/workspace/agents/new`. |
| Agent templates | `GET /api/agent-templates` | Custom copy through `POST /api/agents` | Template cards route into the new-agent form with the source template preselected. |
| Workflows | `GET /api/task-workspaces` | Task workspace create/update/delete/action APIs | Workflow agent selectors now use executable custom agents only, not immutable templates. |
| Models | `GET /api/models` | Model create/update/delete APIs | Existing real config-backed behavior retained. |
| Skills | `GET /api/skills` | Skill create/update/delete/enable APIs | Existing real config-backed behavior retained. |
| MCP | `GET /api/mcp/config` | `POST /api/mcp/servers`, `DELETE /api/mcp/servers/{name}` | Frontend now uses single-server mutations instead of rewriting the full MCP map for add/update/delete. |
| Plugins | `GET /api/plugins/registry` | install/enable/disable/uninstall APIs | Removed the misleading edit button because plugins do not currently expose editable configuration fields. |
| Channels | `GET /api/channels/` | config/enable/delete/restart APIs | Existing real config-backed behavior retained. |

## Firecrawl MCP

Firecrawl cannot start without a real `FIRECRAWL_API_KEY`. The repository now
keeps the Firecrawl MCP entry disabled with the environment placeholder:

```json
{
  "FIRECRAWL_API_KEY": "$FIRECRAWL_API_KEY"
}
```

The MCP API resolves placeholders at runtime. If the key is absent, the server
reports `missing_env: ["FIRECRAWL_API_KEY"]`, and enabled MCP startup fails
closed by skipping that server instead of launching a broken process.

## Long-Running Execution

The session compaction middleware now stores a compact checkpoint in thread
runtime state whenever older conversation history is summarized before a model
call. Later turns inject that checkpoint as hidden system context, allowing the
agent to continue from compressed prior state without requiring the user to
repeat the task.

The compaction budget now follows the selected model's configured
`max_context_tokens` when available, instead of always using a fixed 32k window.
Task workspace LangGraph execution also honors the workspace timeout up to the
existing 7200 second safety cap rather than forcing long runs through a 300
second ceiling.

## WebUI Cleanup

The redundant right-side TaskWorkspace empty-state card was removed. The
Workflow Inspector keeps the important `面板` and `文件` tabs and the execution
console remains intact.

## Verification Snapshot

Commands and checks run during this pass:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/test_session_compaction_middleware.py -q
cd backend && .venv/bin/python -m ruff check src/gateway/routers/agents.py src/gateway/routers/mcp.py src/mcp/client.py src/agents/middlewares/session_compaction_middleware.py src/agents/lead_agent/agent.py src/task_workspaces/execution.py tests/agents/test_session_compaction_middleware.py
cd frontend && pnpm typecheck
```

Live API and browser smoke verification after restart confirmed:

- `/api/agents` returns 78 entries: 10 custom agents and 68 template entries
- `/api/mcp/config` returns Firecrawl `missing_env` for `FIRECRAWL_API_KEY`
- the specific redundant TaskWorkspace empty-state card is absent from the
  right-side inspector
- agent templates are visible in the gallery and prefill the new-agent form
- plugin cards no longer expose a fake edit action

Manual review is still required before production exposure, especially for
credential provisioning and long-running task resource limits.