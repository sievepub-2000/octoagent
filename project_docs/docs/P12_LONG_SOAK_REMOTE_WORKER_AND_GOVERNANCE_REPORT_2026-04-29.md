# P12 Long Soak, Remote Worker, And Governance Report

> Last updated: 2026-04-29

## Scope

This pass implements the next stability plan:

- summarize `backend/reports/chat-regression-trends.jsonl` into readable threshold reports
- start real 2h, 8h, and 24h long-running soak baselines
- monitor long soaks every 10 minutes until completion
- prefer independent distributed execution workers over gateway-local self-dispatch when healthy workers exist
- strengthen operator governance with explicit dangerous-operation confirmations
- reduce frontend governance surface fragmentation with a single operator summary row

## Chat Regression Trend Baseline

Command:

```bash
make chat-regression-report
```

Generated local artifacts:

- `backend/reports/chat-regression-trends-summary.json`
- `backend/reports/chat-regression-trends.md`

Current threshold policy:

| Metric | Threshold | Current observed |
| --- | ---: | ---: |
| Long-scroll max render time | 5000 ms | 3085 ms |
| Minimum long-scroll message count | 520 | 520 |
| Critical browser console errors | 0 | 0 |

Current result: **OK** across 3 recorded chat-regression runs.

## Long Soak Baseline

Command:

```bash
make soak-baseline-suite
```

Started profiles:

| Profile | Duration | PID | State at 2026-04-29T12:38:54Z |
| --- | ---: | ---: | --- |
| 2h | 7200 seconds | 2950549 | completed |
| 8h | 28800 seconds | 2950550 | running |
| 24h | 86400 seconds | 2950551 | running |

The 2h profile completed with `ok=true`. Its final resource sample showed:

- `worker_queued=0`
- `active_runs=0`
- `alerts=0`
- event-loop latency `0.007 ms`
- checkpoints pruned from 60 to 20 in the sampled contract window

Current monitor artifacts:

- `workspace/runtime/soak_reports/soak-suite-20260429T085344Z.json`
- `workspace/runtime/soak_reports/soak-monitor.md`
- `workspace/runtime/soak_reports/soak-monitor.json`
- `workspace/runtime/soak_reports/soak-monitor-loop.log`

The monitor loop was started with a 600-second interval and will keep refreshing until the 24h run completes.

## Distributed Execution

`ExecutionNodeRegistry` now routes healthy independent worker nodes before the gateway-local fallback. The local node remains as the fallback path when no healthy remote worker has capacity.

The worker HTTP dispatch code is now isolated in `_post_worker_dispatch()` and uses `trust_env=False` so host proxy variables cannot break local worker callbacks.

`run_distributed_dispatch_smoke.py` was updated to send the required confirmation header during node cleanup.

## Operator Governance

Existing shared governance helpers already provide:

- operator role checks
- optional shared-token enforcement
- recursive secret redaction
- signed audit events

This pass adds explicit confirmation headers for destructive operator actions:

- execution node removal requires `CONFIRM REMOVE NODE`
- tenant deletion requires `CONFIRM DELETE TENANT`

Frontend operator API calls now send these confirmations for the matching actions.

## Frontend Governance Surface

The Operator Surfaces settings page now has a compact summary row across:

- Runtime metrics
- Distributed execution
- Tenants
- Capability policy

The distributed execution tab also shows recent dispatch history, so operators do not need to move between multiple surfaces to understand worker routing state.

An E2E regression now covers:

- summary row visibility
- distributed dispatch history rendering
- execution-node delete confirmation header
- tenant delete confirmation header

The CI `chat-regression` job runs this test after the live WebUI stack starts.

## Independent Worker Deployment

Independent execution worker deployment materials are now tracked:

- `deploy/octoagent-execution-worker.service`
- `deploy/system/execution-worker.env.example`
- `project_docs/docs/EXECUTION_WORKER_DAEMON_RUNBOOK.md`

The runbook covers install, health checks, gateway registration with `dispatch_token` / `callback_token`, dispatch smoke, systemd operations, and secure token handling.

## Verification Notes

Focused backend regression coverage was added for:

- chat regression trend summary thresholds
- long soak monitor state/report generation
- remote-worker-first distributed routing
- destructive operation confirmation gates
- operator surfaces browser E2E
- execution worker deployment materials

Full verification status is recorded in the task summary after local checks finish.
