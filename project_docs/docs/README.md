# OctoAgent Documentation Index

This directory contains current architecture, status, delivery, and operation guidance for the canonical project root `/home/sieve-pub/public-workspace/octoagent`.

## Start Here

- [`P26_PROJECT_FIRST_WEBUI_REFACTOR_2026-07-13.md`](P26_PROJECT_FIRST_WEBUI_REFACTOR_2026-07-13.md) - project-first WebUI, persistent project context, system panel, and verification baseline
- [`PROJECT_STATUS.md`](PROJECT_STATUS.md) - current module map and implementation status
- [`PROJECT_PROGRESS.md`](PROJECT_PROGRESS.md) - current progress and next delivery steps
- [`ARCHITECTURE.md`](ARCHITECTURE.md) - system architecture and runtime shape
- [`MODULE_PRIORITY_REFACTOR_ROADMAP.md`](MODULE_PRIORITY_REFACTOR_ROADMAP.md) - module closure priority plan
- [`P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md`](P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md) - P0 closure and repository cleanup report
- [`P1_P5_COMPLETION_AND_FULL_CODE_ASSESSMENT_REPORT.md`](P1_P5_COMPLETION_AND_FULL_CODE_ASSESSMENT_REPORT.md) - P1-P5 closure, full code assessment, competitor comparison, and next plan
- [`P6_OPERATIONAL_HARDENING_AND_LONG_RUNNING_ASSESSMENT_2026-04-25.md`](P6_OPERATIONAL_HARDENING_AND_LONG_RUNNING_ASSESSMENT_2026-04-25.md) - lint/doctor/operator-policy closure, full validation, mihomo TUN status, and long-running runtime plan
- [`P7_LONG_RUNNING_RUNTIME_CLOSURE_2026-04-25.md`](P7_LONG_RUNNING_RUNTIME_CLOSURE_2026-04-25.md) - LangGraph contract ledger, checkpoint prune/copy/delete, query maintenance, worker isolation, policy WebUI, and soak validation
- [`P8_ENVIRONMENT_STACK_AND_RUNTIME_HEALTH_CLOSURE_2026-04-25.md`](P8_ENVIRONMENT_STACK_AND_RUNTIME_HEALTH_CLOSURE_2026-04-25.md) - environment stack alignment, LangGraph 0.8.1 validation, runtime maintenance scheduler, Runtime Health WebUI, and full verification record
- [`P9_FINALIZATION_ROADMAP_AND_GOVERNANCE_CLOSURE_2026-04-26.md`](P9_FINALIZATION_ROADMAP_AND_GOVERNANCE_CLOSURE_2026-04-26.md) - uv.lock refresh, workflow/LangGraph lifecycle smoke, long-running soak sampling, Runtime Health notification badge, policy/tenant governance, and final remaining workload
- [`P14_OPERATOR_MODULE_CLOSURE_REPORT_2026-05-06.md`](P14_OPERATOR_MODULE_CLOSURE_REPORT_2026-05-06.md) - operator module closure contract and smoke report
- [`P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md`](P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md) - full repair, CLI/WebUI smoke, accessibility, and validation report
- [`CHANNEL_BRIDGE_DEPLOYMENT_GUIDE.md`](CHANNEL_BRIDGE_DEPLOYMENT_GUIDE.md) - bridge-backed channel deployment guide
- [`DEFAULT_AGENT_PROMPT_STANDARD.md`](DEFAULT_AGENT_PROMPT_STANDARD.md) - canonical default prompt rules
- [`PORTS.md`](PORTS.md) - local runtime port allocation
- [`RELEASE_PACKAGING_AND_MATERIALS.md`](RELEASE_PACKAGING_AND_MATERIALS.md) - release packaging baseline
- [`EMBEDDED_BOOTSTRAP_DEPLOYMENT.md`](EMBEDDED_BOOTSTRAP_DEPLOYMENT.md) - embedded bootstrap deployment guidance

## Interpretation Rules

- Treat `config.example.yaml` as the tracked repository template.
- Treat `config.yaml`, `.env`, logs, build outputs, virtual environments, and runtime workspace data as per-machine local state.
- Treat `main` as the only active branch unless explicitly changed by a future repository policy update.
- Treat deleted numbered stage reports and imported documents as historical content available only through Git history.

## Verification Baseline

After the P18 repair pass, the repository baseline uses backend compile, backend ruff, pytest, frontend lint, frontend typecheck, frontend build, release-readiness contract smoke, system-execution security smoke, operator module closure smoke, mock/real WebUI smoke, management menu smoke, and real browser accessibility checks. The latest browser verification covered hydration, stale chunk recovery, skip link behavior, accessible names, 320px reflow, and forced-colors mode.
