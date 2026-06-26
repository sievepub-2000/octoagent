# Project Status (2026-06-26)

## Runtime Truth

### Services (3/3 UP)
| Service | PID | Port | Status |
|---------|-----|------|--------|
| Gateway API (uvicorn) | 299453 | :19802 | UP (4 workers, sieve-pub user) |
| Frontend (Next.js 16.2.3) | 311875 | :19806 | UP (proxied via nginx :19800) |
| nginx (master) | 51467 | :19800 | UP (HTTP 307 / → /workspace/projects) |

### Pages (8/8 all HTTP 200)
- /workspace/projects — Projects list + CRUD
- /workspace/projects/[project_id] — Project detail / agent conversation
- /workspace/workflows — Redirects to /workspace/projects
- /workspace/workflows/[task_id] — Workflow detail (agent internal)
- /workspace/chats — Chat list
- /workspace/chats/[thread_id] — Chat detail
- /workspace/settings — System settings
- /workspace/evolution — Evolution (system growth)

### APIs (8 endpoints)
| Endpoint | Status |
|----------|--------|
| GET /api/health | 200 |
| GET /api/workspace/projects | 200 |
| POST /api/workspace/projects | 200 (autocreates Lead Agent) |
| GET /api/workspace/projects/{id} | 200 (returns agents[]) |
| PATCH /api/workspace/projects/{id} | 200 |
| DELETE /api/workspace/projects/{id} | 204 |
| POST /api/workspace/projects/{id}/memory | 200 |
| POST /api/workspace/projects/{id}/summaries | 200 |

### MCP Servers (passed=7 failed=0 enabled=7 total=8)
| Server | Status | Notes |
|--------|--------|-------|
| filesystem | OK | Binary from runtime/tools/mcp/node_modules/.bin/ |
| postgres | OK | pg root role trust auth on sieve_pub |
| redis | OK | localhost:6379 PONG |
| docker | OK | DOCKER_MCP_LOCAL=true |
| openapi | OK | Talkes to gateway :19802 |
| http-api | OK | Python local server |
| docker-compose | OK | Python local server |
| kubernetes | DISABLED | kubectl not installed on this host |

### Infrastructure
- **PostgreSQL**: 16.1, 
oot@localhost:5432/sieve_pub, TCP trust auth
- **Redis**: localhost:6379 (PONG OK)
- **Docker**: 29.1.3, daemon running
- **Memory**: workspace/default/memory.json — 6 facts, user+history OK, v2
- **Agent runtime**: LangGraph runtime :19804
- **Project CRUD**: Create → auto-assigns Lead Agent, redirects to conversation view

### i18n
- 5 locales (en-US, zh-CN, zh-TW, ja, ko), 900+ keys each, zero missing
- Projects page fully i18n-aware (17 fields, 22 status label entries)

### Tool Registry Status
- MCP: 7 enabled / 1 disabled (kubernetes)
- Skills: 53 enabled
- Plugins: 16 enabled
- Channels: 3 enabled (need user OAuth config)
- Built-in tools: 110 (40 high-risk — require user approval — expected design)

## Known State
- MCP config uses hardcoded absolute paths (no OCTOAGENT_* env vars on server)
- PostgreSQL auth via TCP trust (not peer) because OS user has hyphen in name
- Kubernetes MCP disabled (binary present, config disabled)
- Project creation auto-assigns 1 Lead Agent via agents[] response
- New projects redirect to conversation work area after creation
- Workflows entry page does client-side redirect to Projects (Next.js 16 RSC redirect() limitation)

