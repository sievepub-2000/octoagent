# P13 Release Readiness Audit Gate - 2026-05-06

## Scope

This pass adds a repeatable release-readiness evidence gate for the remaining OctoAgent production work. The gate does not claim staging success from local files. It turns the current 8-module maturity estimate into checks that can be rerun before release:

- live runtime doctor/API contract evidence
- governance and signed-audit environment evidence
- chat regression trend evidence
- long-running soak monitor evidence
- runtime run-record evidence
- deployment and operator runbook evidence
- regression-safety evidence after source test removal

## Implementation

- Added `backend/scripts/run_release_readiness.py`.
- Added `backend/scripts/run_release_readiness_contract_smoke.py`.
- Added `backend/scripts/run_system_execution_security_smoke.py`.
- Added `make release-readiness` with `RELEASE_READINESS_MIN_SCORE ?= 95`.
- Added `make release-readiness-contract` and `make smoke-system-execution-security`.
- Added system-execution operator/admin auth checks on mutating and CLI routes when `OCTO_OPERATOR_TOKEN` is configured.
- Added optional external evidence manifest ingestion through `--evidence-manifest` so staging, soak, signed audit, rollback, and retention artifacts can close the 95+ gate without being faked locally.
- Generated local JSON/Markdown artifacts under `workspace/runtime/release_readiness/`.
- Updated project status, progress, and audit scorecard documents to make the readiness gate part of the current release baseline.

## Local Evidence Result

Command:

```bash
backend/.venv/bin/python backend/scripts/run_release_readiness.py --json --run-doctor --min-score 0
```

Result:

- Overall evidence score: 80.5 / 100.
- Target score: 95 / 100.
- Live doctor/API contract checks executed.
- The report was written to `workspace/runtime/release_readiness/release-readiness.md`.
- The JSON evidence was written to `workspace/runtime/release_readiness/release-readiness.json`.

The script intentionally returns a failing release state for the default 95 target until the missing staging and production-governance evidence exists.

With an external evidence manifest, the same gate can now evaluate archived staging artifacts. The required manifest keys are:

- `staging_real_conversation`
- `live_doctor_contracts`
- `chat_regression_trend`
- `long_soak_monitor`
- `operator_auth_binding`
- `signed_audit_export`
- `rollback_drill`
- `long_conversation_replay`
- `mobile_accessibility`
- `run_record_audit_page`
- `external_retention`
- `secrets_rotation`
- `regression_gate_bundle`

## Module Scores

| Module | Score | Release blocker |
| --- | ---: | --- |
| 核心对话/多 Agent runtime | 87 | staging real conversation proof and long continuation soak evidence |
| Runtime 治理/审计 | 78 | real auth claim binding and HMAC audit secret |
| 系统操作能力 | 87 | production role mapping and rollback drill evidence |
| 记忆/长上下文 | 89 | fresh long conversation replay artifacts |
| 前端工作台 UX | 86 | mobile/accessibility screenshots and chat trend summary |
| 可观测性 | 77 | run-record audit page, external retention, alert thresholds |
| 部署/发布 | 86 | secrets rotation and nightly soak evidence |
| 回归安全 | 54 | source tests are absent; confidence must come from hard smoke/soak/readiness gates |

## Minimum Work To Claim 95+

1. Run and archive staging real conversation smoke.
2. Complete and archive 2h/8h/24h soak monitor with `ok=true`.
3. Run release readiness with `OCTO_OPERATOR_TOKEN` and `OCTO_OPERATOR_AUDIT_SECRET` configured.
4. Archive mobile/accessibility screenshots and chat regression trend summary.
5. Bind operator identity to real auth claims and export signed audit evidence.

## Verification

Executed in this pass:

```bash
backend/.venv/bin/python -m compileall -q backend/scripts/run_release_readiness.py
backend/.venv/bin/python -m ruff check backend/scripts/run_release_readiness.py
backend/.venv/bin/python backend/scripts/run_release_readiness.py --json --run-doctor --min-score 0
cd backend && .venv/bin/python scripts/run_release_readiness_contract_smoke.py
cd backend && .venv/bin/python scripts/run_system_execution_security_smoke.py
make operator-release
```

The strict release command remains:

```bash
make release-readiness
```

It defaults to `RELEASE_READINESS_MIN_SCORE=95` and is expected to fail until the evidence gaps above are closed.
