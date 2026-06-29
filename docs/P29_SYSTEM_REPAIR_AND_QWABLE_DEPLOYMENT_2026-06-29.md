# P29: System Repair & Qwable-v1 Deployment (2026-06-29)

## Summary
Deployed Qwable-v1-Q8_0 (37.81GB GGUF), fixed SYSTEM_PROMPT_TEMPLATE NameError, started LangGraph service, fixed scrapling/Playwright proxy chain, and resolved systemd service startup cycle.

## Changes

### Model Deployment
- Downloaded `lordx64_Qwable-v1-Q8_0.gguf` (37.81GB) via mihomo proxy to `/llm-server/models/qwable-v1/`
- Restarted llama-server with `-c 262144`, `-fa auto`, `-ctk q8_0`, `-ctv q8_0` — 82-100 t/s prompt, 37-39 t/s gen
- Created startup script: `/llm-server/scripts/start_qwable.sh`

### OctoAgent Config
- Added `qwable-v1-q8-mm-prod` model entry (priority 120, supports_vision: true) to `runtime/config/config.yaml`
- Updated `setup_state.json` and `setup.json` default_model → `qwable-v1-q8-mm-prod`
- Updated `bidpilot/packages/ai/src/index.ts` GB10_MODELS to default Qwable

### Bug Fixes
1. **SYSTEM_PROMPT_TEMPLATE NameError** (`backend/src/agents/lead_agent/prompt.py:299`)
   - Template definition was stripped during prompt refactor but format() call remained
   - Re-added SYSTEM_PROMPT_TEMPLATE + fixed missing format vars (default_design_standard, ml_intern_defaults, capability_section)

2. **TypeScript build failure** (`frontend/src/core/threads/hooks.ts:1369`)
   - `deleteJSON` used but not imported
   - Added `import { deleteJSON } from "../api/http"` — fixed next build

3. **fuser hang in stop-services.sh** (`scripts/stop-services.sh`, `scripts/start-daemon.sh`)
   - `fuser -k ${port}/tcp` hung indefinitely, blocking systemd restart cycle
   - Reordered `kill_port_owners` to use lsof first (doesn't hang), fuser last with timeout 10

4. **scrapling StealthyFetcher missing proxy support** (`backend/src/community/scrapling/tools.py`)
   - `scrapling_fetch_stealth` didn't pass HTTP_PROXY/HTTPS_PROXY to Playwright browser
   - Added `_get_proxy_from_env()` function — StealthyFetcher now uses proxy when available
   - Installed Playwright Chromium (1217) for stealth browsing
   - Set `OCTO_WEB_FETCH_SCRAPLING_STEALTH_ON_BLOCK=1` in .env

### Service Status (all UP)
| Service | Port | Status |
|---------|------|--------|
| llama-server (Qwable-v1) | 8000 | UP |
| nginx | 19800 | UP |
| Gateway API | 19802 | UP |
| LangGraph | 19804 | UP |
| Next.js | 19806 | UP |
| ttyd | 19810 | UP |

### Systemd Service
- `octoagent-local.service` — active, stable
- Fixed startup hang: fuser timeout + lsof reorder
- Fixed build failure: TS import fix
- Frontend: webpack build (turbopack has ENOENT race on this host)
