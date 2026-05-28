# OctoAgent Eval and Agent Loop

## Eval Suites

OctoAgent now defines five task-level evaluation suites in `backend/src/harness/evaluation/octoagent_eval_matrix.json`:

- `bugfix`: reproduce, patch, test, and report a real defect.
- `deploy`: validate compose-backed service deployment readiness.
- `security`: run secret/static/dependency/container checks and rank remediation.
- `db_migration`: inspect schema and migration risk without write access.
- `saas_scaffold`: select auth, billing, storage, observability, and deployment building blocks.

## Repo-Level Coding Loop

The standard coding-agent loop is:

1. `plan`: inspect the repository, identify constraints, and define a minimal patch strategy.
2. `patch`: make focused edits with the existing architecture and style.
3. `test`: run the cheapest meaningful checks first, then broaden when risk requires it.
4. `fix`: iterate on failures without reverting unrelated user changes.
5. `report`: summarize changed files, verification, residual risk, and follow-up work.

## Specialist Agents

The default team model is:

- `planner`: decomposes goals, scopes risk, and owns the task checklist.
- `coder`: edits code and keeps patches focused.
- `operator`: runs services, Docker, SSH, DB, deployment, and smoke checks.
- `reviewer`: reviews diffs, tests, security posture, and regression risk.
- `teacher`: explains decisions and keeps user-facing guidance warm and clear.

## Memory Optimization

Memory already exists in `backend/src/agents/memory` and `workspace/default/memory.v2.json`. The optimization target is not adding another memory layer; it is improving preference extraction, retention governance, and prompt injection so the system preserves user preferences, task history, and interaction tone without polluting permanent memory.
