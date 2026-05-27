# Project Docs Index

## Canonical Project Path

The only active OctoAgent project root on this host is `/home/sieve-pub/public-workspace/octoagent`. Do not use `/home/sieve-pub/codex/octoagent` or `/home/sieve-pub/public-workspace/octoagent-module1-webui-only` as project roots.

`project_docs/` is the active documentation home. Historical imported documents and numbered stage reports were consolidated during the P0 cleanup on 2026-04-25.

## Current Source Of Truth

| Document | Purpose |
| --- | --- |
| `docs/PROJECT_STATUS.md` | Current runtime truth, product boundary, stable surfaces, and known closure areas. |
| `docs/PROJECT_PROGRESS.md` | Current progress, completed work, and next delivery steps. |
| `docs/ARCHITECTURE.md` | System architecture, module map, and runtime shape. |
| `docs/P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md` | Latest full repair, CLI/WebUI smoke, accessibility, and validation report. |
| `docs/P19_SYSTEM_LINKAGE_AND_LONG_EXECUTION_REPAIR_2026-05-12.md` | Runtime management linkage, Firecrawl MCP readiness, and long-running context continuation repair. |
| `docs/P20_PERFORMANCE_TRUST_MEMORY_AND_FULL_VERIFICATION_2026-05-12.md` | WebUI performance optimization, trust-score observation, memory repair, tools hub repair, and full verification report. |
| `docs/P24_AUTONOMOUS_AGENT_CAPABILITY_ENHANCEMENT_2026-05-16.md` | Autonomous system operations tools, security audit, config drift, media probing, and capability enhancement report. |
| `docs/P25_CONFIRMATION_AND_LETTA_MEMORY_INTEGRATION_2026-05-16.md` | Confirmation-gated dangerous capabilities and Letta-style core/archival memory integration. |
| `docs/MODULE_PRIORITY_REFACTOR_ROADMAP.md` | P0/P1/P2/P3 priority order and module closure strategy. |
| `docs/P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md` | P0 closure, cleanup summary, validation, and repository sync notes. |
| `docs/CHANNEL_BRIDGE_DEPLOYMENT_GUIDE.md` | Bridge contract, deployment steps, platform matrix, and security boundary. |
| `docs/DEFAULT_AGENT_PROMPT_STANDARD.md` | Canonical default agent prompt standard. |
| `HARNESS_RESEARCH_POLICY.md` | Source-first web research, soft loop recovery, research closure, and validation baseline. |
| `docs/PORTS.md` | Port allocation and local runtime endpoints. |
| `backend/README.md` | Backend architecture and API surface. |
| `frontend/README.md` | Frontend routes, structure, and development workflow. |

## Current Runtime Stability Addendum

As of 2026-05-11, the active stability baseline includes:

- source test suites removed by operator request; CI uses lint, compile, typecheck, build, runtime hygiene, release precheck, and `make soak-smoke`
- oversized-context continuation notice surfaces as `[system：session is compressing and continuing to act]`
- SQLite checkpointer maintenance hooks for prune/copy/delete-for-runs
- startup repair for repository-owned runtime write paths
- repository-owned local nginx temp directories under `tmp/nginx/*`
- runtime run records exposed through `GET /api/runtime/run-records` and summarized in Runtime Health
- SSRF-safe web fetch validation for private/internal addresses and redirects
- safe CLI `--help` behavior for root scripts and backend smoke scripts
- WebUI smoke timeout recovery for cold Next.js dev compiles
- real browser verification for hydration, stale chunk recovery, skip link, accessible names, 320px reflow, and forced-colors mode

As of 2026-05-12, runtime management pages additionally expose a source-aware
agent catalog, single-server MCP mutations
status, and persisted context compaction checkpoints for longer autonomous
execution. See `docs/P19_SYSTEM_LINKAGE_AND_LONG_EXECUTION_REPAIR_2026-05-12.md`.

Later on 2026-05-12, the WebUI performance pass lazy-loaded heavy settings
sections, reduced status-bar registry fetches, deferred runtime-inspector work
behind the chat first paint, enabled skill trust-score observation, repaired
legacy memory summaries, and validated WebUI/backend/CLI entries. See
`docs/P20_PERFORMANCE_TRUST_MEMORY_AND_FULL_VERIFICATION_2026-05-12.md`.

As of 2026-05-16, the agent runtime includes built-in autonomous operations
tools for runtime health inspection, masked security scanning, configuration
drift checks, and local media metadata probing. See
`docs/P24_AUTONOMOUS_AGENT_CAPABILITY_ENHANCEMENT_2026-05-16.md`.

Later on 2026-05-16, dangerous host-level capabilities were moved behind a
user-confirmation gate, while Letta-style core memory blocks and archival memory
were integrated into the existing memory stack. See
`docs/P25_CONFIRMATION_AND_LETTA_MEMORY_INTEGRATION_2026-05-16.md`.

As of 2026-05-27, user-directed web research follows a source-first harness
policy: named URLs/domains are tried before broad search, repeated execution
steps summarize and change strategy after three repeats, repeated failures skip
and continue after five failures, and research closure uses compacted evidence
plus source-domain-filtered fallback reports instead of normal hard stops. See
`HARNESS_RESEARCH_POLICY.md`.

## Repository Hygiene

- Keep only repository-owned source, scripts, current docs, examples, and deployment assets in version control.
- Keep local-only runtime state out of the repository root, including virtual environments, frontend build output, node modules, logs, editor archives, screenshots, and temporary research outputs.
- Keep generated reports, screenshots, browser output, temporary files, and logs out of Git: `backend/reports/`, `backend/screenshots/`, `frontend/test-results/`, `tmp/`, and `logs/` are local/CI artifacts only.
- Keep `references/README.md` tracked, but treat `references/_clones/` as local-only synchronized study material.
- Use `.env.example`, `config.example.yaml`, and `extensions_config.example.json` as templates; local real config files stay untracked.

## Deprecated Content

The previous `project_docs/imported/`, `project_docs/archive/`, numbered stage reports, duplicate demo outputs, and transient validation reports were removed during cleanup. Use Git history if a deleted historical report is needed for forensic review.
