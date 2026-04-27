# Changelog

## 2026-04-25

- Completed P0 thread recovery: stale LangGraph thread submit failures now retry once in a fresh thread instead of surfacing as an internal error.
- Cleaned repository state: removed tracked backend tests, frontend e2e tests, snapshots, test-only helper prompts, duplicate imported docs, archived stage reports, demo output copies, and transient root reports.
- Consolidated active documentation around `README.md`, `project_docs/README.md`, `project_docs/docs/PROJECT_STATUS.md`, `project_docs/docs/PROJECT_PROGRESS.md`, and `project_docs/docs/P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md`.
- Updated CI, live validation, optimization scorecard, and release precheck gates to use compile, lint, typecheck, build, and smoke validation rather than deleted test trees.
