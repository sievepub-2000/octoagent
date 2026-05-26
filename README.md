# OctoAgent


## Canonical Project Path

The only active OctoAgent project root on this host is `/home/sieve-pub/public-workspace/octoagent`. Do not use `/home/sieve-pub/codex/octoagent` or `/home/sieve-pub/public-workspace/octoagent-module1-webui-only` as project roots; branch and worktree content should be merged into the canonical project root.

OctoAgent is a task-centric multi-agent platform built around a single active runtime path:
Next.js WebUI -> FastAPI gateway -> LangGraph runtime.

Current repository truth:

- active execution provider: LangGraph-only
- backend top-level modules: 45
- gateway router groups: 38 registered groups (41 router files)
- primary workflow truth source: task_workspaces + workflow_core projections
- unified local entrypoint: http://127.0.0.1:19800
- local default model: `openrouter-free-openai-gpt-oss-20b` for flash WebUI dialogue, with quota/cooldown-aware fallback for live WebUI dialogue
- runtime governance version: `2026.5.22`
- systemd startup owner: `/etc/systemd/system/octoagent-local.service` calls only `scripts/start-octoagent.sh`; all OctoAgent child processes are launched and stopped by repository scripts under `scripts/`
- backend Python runtime: one repository venv at `backend/.venv`, exposed to scripts as `OCTOAGENT_PYTHON_BIN`
- repository-scoped tools and maintenance scripts live under `scripts/` and `runtime/`; host-level helper copies under `/usr/local/bin` are not part of the active deployment

Canonical documentation:

- project index: [project_docs/README.md](project_docs/README.md)
- current status: [project_docs/docs/PROJECT_STATUS.md](project_docs/docs/PROJECT_STATUS.md)
- current progress: [project_docs/docs/PROJECT_PROGRESS.md](project_docs/docs/PROJECT_PROGRESS.md)
- P18 full repair and verification: [project_docs/docs/P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md](project_docs/docs/P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md)
- P19 system linkage and long execution repair: [project_docs/docs/P19_SYSTEM_LINKAGE_AND_LONG_EXECUTION_REPAIR_2026-05-12.md](project_docs/docs/P19_SYSTEM_LINKAGE_AND_LONG_EXECUTION_REPAIR_2026-05-12.md)
- P21 context/runtime/repository sync: [project_docs/docs/P21_CONTEXT_RUNTIME_AND_REPOSITORY_SYNC_2026-05-15.md](project_docs/docs/P21_CONTEXT_RUNTIME_AND_REPOSITORY_SYNC_2026-05-15.md)
- P24 autonomous capability enhancement: [project_docs/docs/P24_AUTONOMOUS_AGENT_CAPABILITY_ENHANCEMENT_2026-05-16.md](project_docs/docs/P24_AUTONOMOUS_AGENT_CAPABILITY_ENHANCEMENT_2026-05-16.md)
- P25 confirmation and Letta memory integration: [project_docs/docs/P25_CONFIRMATION_AND_LETTA_MEMORY_INTEGRATION_2026-05-16.md](project_docs/docs/P25_CONFIRMATION_AND_LETTA_MEMORY_INTEGRATION_2026-05-16.md)
- P15 Hermes Gemini/WebUI readiness: [project_docs/docs/P15_HERMES_GEMINI_WEBUI_AND_95_LOCAL_READINESS_2026-05-06.md](project_docs/docs/P15_HERMES_GEMINI_WEBUI_AND_95_LOCAL_READINESS_2026-05-06.md)
- architecture: [project_docs/docs/ARCHITECTURE.md](project_docs/docs/ARCHITECTURE.md)
- module owners (Phase 0 frozen): [project_docs/docs/MODULE_OWNERS.md](project_docs/docs/MODULE_OWNERS.md)
- topology freeze (2026-05-26): [project_docs/docs/TOPOLOGY_FREEZE_2026-05-26.md](project_docs/docs/TOPOLOGY_FREEZE_2026-05-26.md)
- P0 closure and cleanup: [project_docs/docs/P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md](project_docs/docs/P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md)
- local FAISS RAG and semgrep scan workflow: [docs/faiss-rag-and-semgrep-scan.md](docs/faiss-rag-and-semgrep-scan.md)
- one-line install and CLI: [docs/one-line-install-and-cli.md](docs/one-line-install-and-cli.md)
- channel bridge deployment: [project_docs/docs/CHANNEL_BRIDGE_DEPLOYMENT_GUIDE.md](project_docs/docs/CHANNEL_BRIDGE_DEPLOYMENT_GUIDE.md)


## One-Line Install And CLI

From a Linux host with network access, the service install path can be bootstrapped with:

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-octoagent.sh | bash -s -- --prefix /home/sieve-pub/public-workspace/octoagent --user sieve-pub --mode service --yes --start
```

After installation, `octoagent` starts the full stack. `octoagent configure` updates the repository setup state for the default model, and `octoagent ports` prints the active port map. See [docs/one-line-install-and-cli.md](docs/one-line-install-and-cli.md).

## Production Hardening Before Launch

Set these environment variables before exposing the service beyond a trusted local network:

- `OCTO_OPERATOR_TOKEN`: required shared token for operator/admin governance endpoints when configured.
- `OCTO_EXECUTION_WORKER_TOKEN`: required shared token for distributed worker dispatch and callbacks when configured.
- `OCTO_OPERATOR_AUDIT_SECRET`: HMAC key for signed governance audit events. Without it, audit signatures are plain SHA-256 checksums.
- `OCTO_RUNTIME_MAX_RUNNING_RUN_AGE_SECONDS`: stale LangGraph run ledger timeout, default `3600`. Runtime maintenance marks older abandoned running records as `timeout` so long-running soak checks can settle.
- `OCTO_SMTP_HOST`, `OCTO_SMTP_PORT`, `OCTO_SMTP_USERNAME`, `OCTO_SMTP_PASSWORD`, `OCTO_SMTP_FROM`, `OCTO_SMTP_TLS`: SMTP settings for the built-in user email verification flow. Without SMTP, verification codes are logged for local development only.
- `OCTO_AUTH_DEV_EXPOSE_CODES`: keep unset or `0` in production. Setting `1` returns verification codes in API responses for local smoke tests only.

The repository keeps local development compatible when the tokens are unset, but production deployments should set all production secrets and rotate any values that have been exposed in local `.env` files.

## Runtime Governance Notes (2026-05-22)

The 2026-05-22 governance pass keeps the 2号机 deployment and the Git repository aligned around one startup and environment stack:

- systemd owns only `octoagent-local.service`; the unit delegates startup and shutdown to `scripts/start-octoagent.sh` without separate `ExecStartPre` helper scripts or drop-ins
- `scripts/start-octoagent.sh run` performs repository-owned runtime preparation, then starts every OctoAgent component through `scripts/start-daemon.sh`
- Python entrypoints use `backend/.venv/bin/python` through `OCTOAGENT_PYTHON_BIN`; LangGraph, Gateway, nginx config rendering, and frontend build helpers share that same backend environment
- former host helper scripts `octoagent-monitor.sh` and `octoagent-cleanup.sh` live under `scripts/` and are repository-scoped
- cleanup removes repository caches, pyc files, temporary files, and stale `/tmp/octoagent*` probes while preserving required dependency/runtime stores such as `backend/.venv`, `frontend/node_modules`, and production `.next` assets

## Full Repair And Verification Notes (2026-05-11)

## Autonomous Capability Enhancement Notes (2026-05-16)

The 2026-05-16 pass adds a built-in system operations tool layer for autonomous
agent work: runtime health reports, masked security scanning, configuration
drift snapshots/checks, and local media metadata probing. These tools complement
the existing cron, hook, memory, subagent, workflow, Codex CLI, image processing,
document conversion, and web acquisition surfaces without adding another runtime
service or external daemon.

See [project_docs/docs/P24_AUTONOMOUS_AGENT_CAPABILITY_ENHANCEMENT_2026-05-16.md](project_docs/docs/P24_AUTONOMOUS_AGENT_CAPABILITY_ENHANCEMENT_2026-05-16.md).

## Confirmation And Letta Memory Notes (2026-05-16)

Dangerous host-level abilities are now available through explicit user
confirmation rather than being globally unavailable. Letta-style core memory
blocks and archival memory are integrated into the existing OctoAgent memory
stack without adding a separate Letta service.

See [project_docs/docs/P25_CONFIRMATION_AND_LETTA_MEMORY_INTEGRATION_2026-05-16.md](project_docs/docs/P25_CONFIRMATION_AND_LETTA_MEMORY_INTEGRATION_2026-05-16.md).

## Context Runtime And Repository Sync Notes (2026-05-15)

The 2026-05-15 pass repaired the long-context local-model failure mode found in
the latest historical LangGraph thread, normalised runtime identity and writable
path ownership for the `sieve-pub` daemon user, configured Google provider
credentials in local ignored `.env`, and cleared the backend Ruff/PEP8 baseline.

Source and tests remain tracked for repository sync; local runtime state under
`backend/runtime/` and `workspace/self_evolution/` is intentionally ignored.
See [project_docs/docs/P21_CONTEXT_RUNTIME_AND_REPOSITORY_SYNC_2026-05-15.md](project_docs/docs/P21_CONTEXT_RUNTIME_AND_REPOSITORY_SYNC_2026-05-15.md).

The 2026-05-11 repair pass hardens the local production path and records a fresh validation baseline:

- model fallback, subagent/workflow wiring, and tool recovery were repaired and covered by backend tests
- SSRF-safe web fetch behavior now validates private/internal network addresses and redirects fail closed
- sidebar width cookie handling no longer causes hydration mismatch on first client render
- root layout includes stale Next chunk recovery for failed `/_next/static/` script or CSS loads
- CLI and Makefile smoke entrypoints now expose safe help output and run their documented checks
- `run_webui_smoke.py` honors configured navigation timeout for cold Next.js dev compiles
- `/workspace/agents/new` form controls now have accessible names and non-interactive status indicators are no longer focusable buttons
- real WebUI verification covered chat, configuration, agent, workflow, management, 320px reflow, skip link, hydration, chunk recovery, and forced-colors mode

See [project_docs/docs/P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md](project_docs/docs/P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md) for the validation matrix.

## System Linkage And Long Execution Notes (2026-05-12)

The 2026-05-12 pass connects management surfaces to real runtime inventory and
improves long-running task continuity:

- `/workspace/agents` now shows custom agents and installed skill-exported
	agent templates; templates create custom copies before chat or workflow use.
- MCP add/update/delete uses single-server APIs, and unresolved environment
	variables are surfaced in readiness status.- Plugin cards no longer expose a fake edit action; the real supported actions
	are install, enable, disable, and uninstall.
- Workflow agent selectors use executable custom agents only.
- Session compaction stores a runtime checkpoint and injects it into later turns
	so long tasks can continue after older dialogue is compressed.

See [project_docs/docs/P19_SYSTEM_LINKAGE_AND_LONG_EXECUTION_REPAIR_2026-05-12.md](project_docs/docs/P19_SYSTEM_LINKAGE_AND_LONG_EXECUTION_REPAIR_2026-05-12.md) for the repair report and verification snapshot.

## Runtime Speed And Stability Notes (2026-05-07)

The 2026-05-07 pass makes WebUI dialogue cheaper to render and cheaper to answer:

- Flash-mode simple turns skip the extra client pre-planning request unless execution, file, repository, or system work is detected.
- Flash-mode dialogue is pinned to the fast free model path and ignores stale slow-model browser overrides such as `nemotron-3-super-free`.
- Dialogue routing now classifies each turn as `direct_answer`, `current_snapshot`, `current_research`, `tool_action`, or `deep_agent`. The route controls model choice, prompt depth, tool binding, and memory writes.
- Short flash-mode turns skip heavy memory summarisation unless the user explicitly asks the system to remember a preference or fact.
- Current weather and X/Twitter trend requests use compact server snapshots; weather snapshots are resolved per city with Open-Meteo retries and a `wttr.in` fallback.
- Snapshot-backed turns can now answer directly from the structured runtime payload without making an LLM call. This keeps simple weather/trend tasks bounded by data-fetch latency instead of model latency.
- Long chat histories render a bounded active window by default, with an explicit "show earlier messages" control for old turns. This keeps browser DOM, markdown, and streaming work bounded during long sessions.
- Stream watchdog timers are cleared both when server messages arrive and when the SDK reports the run is no longer loading.
- Model routing keeps failed or quota-exhausted models on a short persistent cooldown and falls back automatically.
- `make stop` drains local nginx, gateway, frontend, LangGraph, stale port listeners, and stale `backend/.langgraph_api` state before a clean restart.

## Runtime Stability Notes (2026-04-29)

The current chat runtime hardening pass focuses on long-running conversation stability, context-window safety, and real-browser regression coverage.

### Chat And Context Safety

| Area | Current behavior |
| --- | --- |
| Tool registry | `web_search` is registered as a first-class tool alias and duplicate tool names are rejected before execution. |
| Context guard | Oversized tool, human, and assistant messages are safely truncated before model calls that would exceed context limits. |
| UI observability | Host memory pressure and context-window trimming are reported separately so context truncation is not shown as a memory-guard failure. |
| Subtask state | Ordinary tools no longer write into the subtask store; only `task` tool calls are mirrored as subtasks. |
| Long conversation rendering | The message list uses ordinary scrolling plus `content-visibility` containment. A 520-message browser scroll regression is passing, so no virtual list is currently required. |

### Runtime Persistence And Permissions

| Area | Current behavior |
| --- | --- |
| LangGraph checkpointer | SQLite async saver is wrapped with `adelete_for_runs`, `acopy_thread`, and `aprune` maintenance hooks. |
| Maintenance telemetry | Checkpointer maintenance calls now log and expose per-operation counters through the wrapper. |
| Runtime directories | Gateway startup repairs writable runtime paths such as `backend/.octoagent`, `workspace/runtime`, `workspace/env`, and workflow state directories. |
| nginx local temp files | Local nginx uses repository-owned `tmp/nginx/*` temp paths instead of system `/var/lib/nginx/*` paths. |

### Web Fetch TLS Handling

`web_fetch` (`backend/src/community/ddg/tools.py`) and `scrapling_fetch`
(`backend/src/community/scrapling/tools.py`) verify TLS certificates by default.
For `web_fetch`, OctoAgent builds an explicit verification context using
`truststore` when available and falls back to `certifi`; this follows HTTPX's
official `verify=<SSLContext>` path. For Scrapling/curl-cffi, the tool uses
the official requests-style `verify` option.

Some public sites serve an incomplete certificate chain. When the first request
fails specifically with certificate verification errors, OctoAgent retries the
same public URL with certificate verification disabled, matching the documented
HTTPX/curl-cffi `verify=False` escape hatch. Results are marked so the model and
user can see the downgrade: `web_fetch` prepends a TLS warning, and
`scrapling_fetch` returns `tls_verification=disabled_after_certificate_error`.

Operators can disable the insecure retry with
`OCTO_WEB_FETCH_ALLOW_INSECURE_SSL_RETRY=0` or
`OCTO_SCRAPLING_ALLOW_INSECURE_SSL_RETRY=0`. `OCTO_WEB_FETCH_SSL_VERIFY=0`
disables the initial verified HTTPX context entirely and should only be used for
controlled local debugging.

### Browser Regression Coverage

`make smoke-chat-regression` now exercises the real WebUI through nginx and LangGraph:

- new chat shell
- stale thread route recovery
- continuation route shell
- ordinary tool-call history
- `web_search -> web_fetch/read_webpage` history
- context guard visible notice
- multi-turn and continuation history
- 520-message long-scroll pressure
- right-side Artifact and execution panel desktop/mobile screenshots

The command writes local-only artifacts that are intentionally ignored by Git:

- `backend/reports/chat-regression-trends.jsonl`
- `backend/screenshots/right-panel-visual/`

## Local Verification Commands

Use these commands before merging runtime or UI changes:

```bash
cd backend && make lint
cd backend && .venv/bin/python -m compileall -q src scripts
cd backend && .venv/bin/python scripts/run_system_doctor.py --skip-git
cd backend && .venv/bin/python scripts/run_system_execution_security_smoke.py
cd backend && .venv/bin/python scripts/run_operator_module_closure_smoke.py
cd backend && .venv/bin/python scripts/run_release_readiness_contract_smoke.py

cd frontend && pnpm lint
cd frontend && pnpm typecheck
cd frontend && pnpm build

make clean-stale-logs
make smoke-chat-regression
cd backend && .venv/bin/python scripts/run_webui_smoke.py --frontend-url http://127.0.0.1:19800 --gateway-url http://127.0.0.1:19800 --timeout-seconds 180
make operator-release
make release-readiness
```

Source-level test trees were intentionally removed by operator policy. Release confidence now relies on compile/lint/build, doctor/API contract smoke, real browser smoke, bounded or long soak, system-execution security smoke, release-readiness contract smoke, and the strict `make release-readiness` evidence gate. CI also runs `chat-regression` and uploads browser screenshots, trend JSONL, and runtime logs as the `chat-regression-artifacts` artifact.

## Operational Notes

System log rotation is managed by logrotate via [deploy/system/logrotate.d/octoagent](deploy/system/logrotate.d/octoagent). Install it once with:

```bash
sudo install -o root -g root -m 0644 deploy/system/logrotate.d/octoagent /etc/logrotate.d/octoagent
sudo logrotate -d /etc/logrotate.d/octoagent
```

For local verification, `make clean-stale-logs` truncates old runtime logs so current scans are not polluted by historical errors.

— Updated 2026-05-22
