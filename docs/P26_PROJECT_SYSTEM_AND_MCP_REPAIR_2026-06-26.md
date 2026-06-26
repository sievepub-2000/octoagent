# OctoAgent Project System & MCP Repair

Date: 2026-06-26
Type: Repair, Migration, Verification

## Summary

Replaced the placeholder /workspace/workflows entry page with a client-side redirect to
/workspace/projects, built a full Project CRUD system (list/create/edit/delete) with i18n,
repaired all 8 MCP servers (7/7 passed, 1 disabled), and performed a full-system verification.

## Changes

### 1. Workflow Entry → Project Entry Migration

- /workspace/workflows/page.tsx: replaced server redirect (Next.js 16 redirect() — broken in RSC)
  with "use client" component using useRouter().replace('/workspace/projects').
- /workspace/workflows/[task_id]: preserved for agent/LangGraph runtime internal use.

**Files:**
- rontend/src/app/workspace/workflows/page.tsx — client-side redirect
- rontend/src/app/workspace/projects/page.tsx — Project CRUD, i18n, status badges
- rontend/src/app/workspace/projects/[project_id]/page.tsx — project detail route → renders TaskWorkspaceBoardSingleCard
- rontend/src/components/workspace/task-workspace-board-single-card.tsx — project detail / agent conversation
- ackend/src/gateway/routers/projects.py — project CRUD + memory + summaries endpoints
- rontend/src/core/i18n/workspace-copy.ts — i18n strings for ProjectsPageCopy (17 fields × 5 locales = 85 entries)

### 2. MCP Server Repair

**Root cause:** extensions_config.json used $OCTOAGENT_* env vars but server had none set.
All 8 MCP servers errored with stdio_command_missing.

**Fix:** Replaced all $VAR references with absolute paths:
- npm binaries: 
untime/tools/mcp/node_modules/.bin/<server>
- Python servers: ackend/.venv/bin/python -m src.tools.mcp.local_servers.<name>
- backend path: /home/sieve-pub/public-workspace/octoagent/backend

**Specific fixes:**
- **PostgreSQL**: created 
oot PG role, set TCP trust in pg_hba.conf, reloaded
- **Kubernetes**: disabled (enabled=false, kubectl not installed)
- **Docker-compose/http-api**: Python local servers, added PYTHONPATH

**Files:**
- rontend/../extensions_config.json — absolute paths
- ackend/src/runtime/config/extensions_config.py — config loader (no change needed)

### 3. Full-System Verification

| Check | Result |
|-------|--------|
| Services | gateway PID=299453, frontend PID=311875, nginx PID=51467 |
| Pages (8) | All HTTP 200 |
| APIs (8) | All HTTP 200/204 |
| MCP | passed=7 failed=0 enabled=7 total=8 |
| Memory | facts=6, user+history OK, version=2 |
| Project CRUD | create/read/delete OK, auto-assigns 1 Lead Agent |
| Nginx | HTTP 307 (root → /workspace/projects) |

## Key Decisions

- **Client-side redirect** over 
edirect(): Next.js 16 RSC 
edirect() throws
  digest=1698646601 ("Could not find the module in the React Client Manifest").
  Using "use client" + useRouter().replace().

- **Hardcoded paths** in MCP config: server has no $OCTOAGENT_* env vars, no .bashrc/.profile.
  Hardcoding avoids modifying system env config.

- **TCP trust** for PostgreSQL: unix-socket peer auth requires OS user to match PG role;
  but OS user sieve-pub contains a hyphen (invalid PG role name).

- **Kubernetes disabled**, not removed: binary entry preserved in config with
  enabled=false + smokeTest.enabled=false for clean re-enable when kubectl is installed.

## Current State

- Projects entry point works: list → create → auto-redirect to conversation work area
- All 7 enabled MCP servers pass smoke test: startup, schema, list_tools, minimal_call
- i18n: 17 projects page fields in 5 locales (en-US, zh-CN, zh-TW, ja, ko)
- Tool registry: 7 MCP enabled, 53 skills, 16 plugins, 3 channels (need OAuth), 110 builtin tools
