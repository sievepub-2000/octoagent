# P15 Hermes Gemini WebUI And 95 Local Readiness Report - 2026-05-06

## Summary

P15 configured the 2号机 OctoAgent WebUI/API default model from 3号机 Hermes model metadata and closed the remaining local WebUI/runtime stability issues found during live verification.

The local module/functionality readiness target is now above 95% for the checked OctoAgent runtime path: WebUI -> Gateway -> LangGraph, with live API module probes, real browser WebUI smoke, operator release, and model fallback dialogue all passing. The strict production release readiness gate remains evidence-gated at 81.5 / 100 because it intentionally requires external staging/soak/audit/retention artifacts before claiming production 95+.

## Hermes Model Import

Source checked on 3号机 Hermes:

- Hermes config provider: `gemini`
- Hermes default model: `gemini-3-pro-preview`
- Hermes API base: `https://generativelanguage.googleapis.com/v1beta`
- Hermes catalog target: `gemini-3.1-pro-preview` / `google/gemini-3.1-pro-preview`
- Catalog capabilities: reasoning/tool-call capable, vision capable, 1,048,576 context tokens, 65,536 output tokens

OctoAgent local model configured on 2号机:

- model name: `hermes-gemini-3.1-pro`
- provider: `google`
- interface: `google_genai`
- route model: `gemini-3.1-pro-preview`
- default model in setup state: `hermes-gemini-3.1-pro`
- fallback chain: `qwen3.6-plus`, `gpt-5.4-paid`, `qwen3-next-free`

Secrets stay in local `.env` and are not committed.

## Fixes Landed

- `scripts/start-daemon.sh` now loads repo-local `.env` before daemonizing services.
- `scripts/start-daemon.sh` preserves HTTP(S) proxy egress from `.env` while still clearing SOCKS/FTP proxy variables that model clients reject.
- `docker/nginx/nginx.local.conf.template` now applies 600s proxy timeouts to `/api/` so model fallback requests are not cut off by nginx.
- `backend/src/system_guard/service.py` now skips signal-handler registration outside the main thread, fixing gateway/TestClient/WebUI smoke startup noise.
- Added `backend/tests/system_guard/test_system_guard_service.py` to lock the non-main-thread SystemGuard behavior.

## Live Findings

- 2号机 mihomo is healthy on `127.0.0.1:7890`. Direct Google Gemini calls from 2号机 require this HTTP proxy.
- 3号机 can list Gemini models directly; `gemini-3.1-pro-preview` is available to the Hermes API key.
- 2号机 can list Gemini models through mihomo; `gemini-3.1-pro-preview` is available.
- Generation against `gemini-3.1-pro-preview` currently returns Google `429 RESOURCE_EXHAUSTED` for this key/model quota. OctoAgent therefore correctly falls back to `qwen3.6-plus` for live dialogue while keeping Hermes Gemini as the configured default.

## Verification

Passed:

```bash
cd backend && .venv/bin/python -m pytest tests/system_guard/test_system_guard_service.py -q
CI=true make operator-release
cd backend && .venv/bin/python scripts/run_webui_smoke.py --frontend-url http://127.0.0.1:19880 --gateway-url http://127.0.0.1:19880 --timeout-seconds 180
backend/.venv/bin/python backend/scripts/run_release_readiness.py --json --run-doctor --min-score 0
```

Observed results:

- SystemGuard regression test: `1 passed`.
- Operator release: `ok=true`, 16/16 steps passed.
- WebUI real smoke: `backend_ok=true`, `frontend_ok=true`, chat send, multi-turn send, continuation route, settings page, bootstrap section, task workspace create/cleanup all passed.
- WebUI dialogue suggestions through `http://127.0.0.1:19880/api/threads/.../suggestions` returned 3 Chinese follow-up questions.
- Runtime setup status: workspace ready, default model `hermes-gemini-3.1-pro`, LangGraph reachable, 15 configured models.
- Module API probe passed for capability inventory/runtime/policies, hooks, tenants/governance, execution nodes, metrics, reflection, evolution, skill evolution, system execution config, browser runtime, research runtime, and long-running runtime health.
- Strict release readiness evidence score: `81.5 / 100`, target `95`, `ok=false` by design until external staging/prod evidence is supplied.

## Current Development Progress

Local checked implementation progress is above 95% for the active runtime and operator module set:

- default model/config path: closed locally, with quota-aware fallback
- WebUI/API functional path: closed locally
- operator substrate modules: closed locally via `make operator-release`
- daemon startup/runtime stability: closed locally
- proxy/model egress: closed locally through `.env` + mihomo HTTP proxy

Production release progress remains gated by evidence rather than code completion. The remaining production-only work is the same strict release-readiness artifact set: staging real conversation, long soak evidence, signed audit export, rollback drill, long replay, mobile/accessibility screenshots, run-record retention, secrets rotation, and archived regression bundle.
