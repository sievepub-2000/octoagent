# P26 project-first WebUI refactor

Release: 2026.7.8
Date: 2026-07-13

## Outcome

OctoAgent now presents a compact engineering workspace centered on projects and tasks. Public workflow authoring and workflow-centric inspection were removed; internal orchestration remains available to the agent runtime.

## Delivered

- Independent JSON-backed Project service with safe root validation and atomic persistence.
- Project Git metadata, instructions, model/permission defaults, archive state, pinned files, and isolated memory.
- Project detail task list and project-scoped new-task links.
- Simplified primary sidebar with project/task hierarchy.
- Activity / Files / System context panel with live host metrics and service state.
- Flat shadcn-style surfaces and a compact welcome state.
- Secure proxy/TLS web-tool repairs and UTF-8 subprocess corrections.
- Deleted 2,600+ lines of unused workflow inspector and task-workspace presentation code.

## Verification baseline

- Backend Ruff: pass.
- Backend focused pytest: 11 passed.
- Frontend ESLint: 0 errors, 0 warnings.
- TypeScript: pass.
- Next.js production build: pass.
- Runtime API: pass (`overall=ok`, both required services active, DNS-over-TLS on).
- Browser smoke: pass for Projects, new task, existing task, Activity, and System tabs; no console warnings or errors observed.

## Compatibility

Legacy workflow and task URLs redirect to `/workspace/projects`. Advanced configuration routes remain available through Settings. Existing runtime workflow state is not deleted or migrated because it is an internal execution concern.
