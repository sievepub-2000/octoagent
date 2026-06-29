# Project Status (2026-06-29)

## Runtime Truth

### Services (6/6 UP)
| Service | PID | Port | Status |
|---------|-----|------|--------|
| llama-server (Qwable-v1-Q8_0) | 736079 | :8000 | UP (262k ctx, q8_0 kv cache) |
| Gateway API (uvicorn) | 870858 | :19802 | UP |
| LangGraph | 870785 | :19804 | UP (4 workers) |
| Frontend (Next.js 16.2.3) | 871225 | :19806 | UP (webpack build) |
| nginx (master) | 871249 | :19800 | UP (proxies /api → :19802, /api/langgraph → :19804, / → :19806) |
| ttyd | 871255 | :19810 | UP |

### Default Model
**qwable-v1-q8-mm-prod** — Qwable-v1-Q8_0 GGUF, supports_vision: true, priority 120
Fallback: qwen36-35b-a3b-ud-q5_k_xl

### Web Fetch Tool Chain
- Primary: httpx + readability extraction (honours HTTP_PROXY/HTTPS_PROXY)
- Anti-bot fallback: scrapling HTTP Fetcher (curl_cffi TLS impersonation)
- Stealth fallback: scrapling StealthyFetcher (Playwright Chromium, `OCTO_WEB_FETCH_SCRAPLING_STEALTH_ON_BLOCK=1`)
- Proxy: all layers pass HTTPS_PROXY=http://127.0.0.1:7897

### Known Issues
- Next.js Turbopack `ENOENT` race on `_buildManifest.js.tmp` during prod build — using webpack (`--webpack`) works around it
- Frontend nginx proxy temp dirs may have permission issues after root/sieve-pub user switches
- Postgres auth via TCP trust (not peer) due to hyphen in OS username
- Kubernetes MCP disabled (binary present, config disabled)

### Recent Bug Fixes
1. `SYSTEM_PROMPT_TEMPLATE` NameError — re-added missing template definition (2026-06-29)
2. `deleteJSON` TS import — added missing import in hooks.ts (2026-06-29)
3. `fuser -k` hang — reordered kill_port_owners to lsof first (2026-06-29)
4. scrapling stealth proxy — added env proxy support (2026-06-29)
