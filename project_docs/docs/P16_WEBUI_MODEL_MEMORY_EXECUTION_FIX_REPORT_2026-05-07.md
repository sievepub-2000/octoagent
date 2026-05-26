# P16 WebUI Model, Memory, Execution Fix Report (2026-05-07)

## Scope

This report records the 2026-05-07 stabilization pass for the OctoAgent WebUI and runtime path.
The pass focused on model-selection consistency, server-side configuration loading for remote access,
long-running task behavior, memory visibility/injection, default subagent roles, and right-panel layout simplification.

## Root Causes

1. The production frontend was built with stale direct `NEXT_PUBLIC_BACKEND_BASE_URL` and
   `NEXT_PUBLIC_LANGGRAPH_BASE_URL` values. Remote or ingress access through `:19880` therefore attempted to
   call old localhost ports (`19832`/`19824`), so model/setup/runtime data looked empty in the browser.
2. The model selector presented system-default models before per-chat override models. Users naturally clicked the
   checked default model and expected chat-level switching, but that action was changing or reading global-default state.
3. Runtime telemetry preferred persisted thread runtime fields over the active server/default model, so an old run could
   keep showing `NVIDIA: Nemotron 3 Super (free)` after the configured default had become Hermes Gemini.
4. The frontend watchdog stopped a run after 30 seconds with `thread.stop()`. Long agent jobs should be observed and
   refreshed, not cancelled by the UI.
5. Settings -> Memory only rendered working-memory facts. System RAG memory could be active and populated while the UI
   still looked empty.
6. Simple conversational messages were labelled as repository-read operations, and news/current-events requests had no
   explicit convergence guidance when search results were irrelevant.
7. The right inspector had a separate canvas tab even though the panel view already embeds the graph canvas, creating a
   duplicated navigation surface.

## Changes

- Startup now clears explicit `NEXT_PUBLIC_*` direct backend/LangGraph URLs before frontend production build unless
  `OCTO_USE_EXPLICIT_NEXT_PUBLIC_URLS=1` is set, forcing local/LAN browser traffic through the current ingress origin.
- Welcome/setup now trusts the server setup status and skips stale browser-local initialization when the server already
  has a ready workspace and default model.
- The model selector now puts `This Chat` first and keeps system-default mutation in a separate lower section.
- Runtime telemetry now prefers the current chat override or server default model over stale thread runtime model fields.
- The 30-second frontend watchdog is now a long-running monitor: it shows a status toast, polls thread state, and keeps
  the run alive instead of stopping it.
- The inspector keeps the panel and files tabs; the graph canvas remains integrated inside the panel view.
- Agency Agents templates are loaded as default `agency-*` subagent role configurations.
- Memory API now mirrors system RAG entries into the Memory page fact list, and the lead-agent prompt injects recent
  long-term/self-evolution memory alongside working memory.
- Query planning now classifies simple conversational turns as `conversation` and routes `x.com`/Twitter/top-news style
  requests to browser runtime.
- Prompt governance now instructs the agent to answer simple requests directly and to converge current-news searches with
  fresh sources instead of silently looping on irrelevant results.

## Verification

- `python3 -m compileall -q backend/src`: pass.
- `pnpm --dir frontend typecheck`: pass.
- `backend/.venv/bin/python -m pytest backend/tests -q`: pass (`1 passed`).
- Production rebuild and daemon restart through `make stop && make start-daemon`: pass.
- WebUI Playwright smoke on `http://127.0.0.1:19880/workspace/chats/new`:
  - no stale setup wizard;
  - no requests to old `19832`/`19824` ports;
  - model button shows `????: Hermes Gemini 3.1 Pro`;
  - runtime panel shows primary model `Hermes Gemini 3.1 Pro`;
  - right inspector has panel/files only, no separate canvas tab;
  - chat-level model switch to `Qwen 3.6 Plus` works while server default remains `hermes-gemini-3.1-pro`.
- API verification:
  - `/api/setup/status` reports `workspace_ready=true`, `configured_default_model=hermes-gemini-3.1-pro`, `models_configured=37`;
  - `/api/memory/system/stats` reports 108 active conversation-summary memories;
  - `??????` plans as `conversation`;
  - `??? x.com ????` plans as `browser_runtime`.
- WebUI response smoke created thread `ba175049-3b0d-4e05-86f4-f75fcc8fd380`; backend state received an AI response:
  `OctoAgent WebUI smoke OK.`

## Operational Notes

- Default model remains Hermes Gemini 3.1 Pro.
- LAN access should use `http://192.168.110.2:19880` or the equivalent ingress host, not direct backend ports.
- Operators who intentionally need fixed public frontend URLs can set `OCTO_USE_EXPLICIT_NEXT_PUBLIC_URLS=1`.
