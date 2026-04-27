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
- unified local entrypoint: http://127.0.0.1:19880

Canonical documentation:

- project index: [project_docs/README.md](project_docs/README.md)
- current status: [project_docs/docs/PROJECT_STATUS.md](project_docs/docs/PROJECT_STATUS.md)
- current progress: [project_docs/docs/PROJECT_PROGRESS.md](project_docs/docs/PROJECT_PROGRESS.md)
- architecture: [project_docs/docs/ARCHITECTURE.md](project_docs/docs/ARCHITECTURE.md)
- P0 closure and cleanup: [project_docs/docs/P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md](project_docs/docs/P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md)
- channel bridge deployment: [project_docs/docs/CHANNEL_BRIDGE_DEPLOYMENT_GUIDE.md](project_docs/docs/CHANNEL_BRIDGE_DEPLOYMENT_GUIDE.md)


## Production Hardening Before Launch

Set these environment variables before exposing the service beyond a trusted local network:

- `OCTO_OPERATOR_TOKEN`: required shared token for operator/admin governance endpoints when configured.
- `OCTO_EXECUTION_WORKER_TOKEN`: required shared token for distributed worker dispatch and callbacks when configured.
- `OCTO_OPERATOR_AUDIT_SECRET`: HMAC key for signed governance audit events. Without it, audit signatures are plain SHA-256 checksums.
- `OCTO_RUNTIME_MAX_RUNNING_RUN_AGE_SECONDS`: stale LangGraph run ledger timeout, default `3600`. Runtime maintenance marks older abandoned running records as `timeout` so long-running soak checks can settle.
- `OCTO_SMTP_HOST`, `OCTO_SMTP_PORT`, `OCTO_SMTP_USERNAME`, `OCTO_SMTP_PASSWORD`, `OCTO_SMTP_FROM`, `OCTO_SMTP_TLS`: SMTP settings for the built-in user email verification flow. Without SMTP, verification codes are logged for local development only.
- `OCTO_AUTH_DEV_EXPOSE_CODES`: keep unset or `0` in production. Setting `1` returns verification codes in API responses for local smoke tests only.

The repository keeps local development compatible when the tokens are unset, but production deployments should set all production secrets and rotate any values that have been exposed in local `.env` files.

## Performance Optimizations (v3.34+)

This release includes a comprehensive set of long-conversation performance improvements across both backend and frontend:

### Backend

| Module | Change | Impact |
|--------|--------|--------|
| `backend/src/agents/memory/cleanup.py` | Periodic TTL eviction, confidence-floor pruning, namespace-cap enforcement (hourly, daemon thread) | Prevents unbounded DuckDB growth across long sessions |
| `backend/src/agents/memory/system_rag_store.py` | In-process LRU search cache (max 200 entries, 5-min TTL) | Eliminates repeated embedding+DuckDB round-trips for identical queries |
| `backend/src/agents/middlewares/session_compaction_middleware.py` | Tiered compaction strategy: ratio <2× → truncate, 2–4× → hybrid, >4× → summarize | Context window managed proportionally to actual pressure |
| `backend/src/agents/degradation.py` | CPU/memory pressure monitor via psutil (DegradationController, 5-s cache) | Exposes `get_degradation_level()` for adaptive throttling |
| `backend/src/gateway/lifecycle.py` | Memory cleanup scheduler wired into FastAPI lifespan | Scheduler runs automatically on gateway startup |
| `backend/src/gateway/routers/metrics.py` | `GET /api/metrics/memory-health` — store stats, scheduler status, degradation level | Observability endpoint for ops dashboards |

### Frontend

| Component | Change | Impact |
|-----------|--------|--------|
| `frontend/src/components/workspace/messages/message-list.tsx` | react-virtuoso virtual scroll + `followOutput="auto"` | Only renders visible messages — O(viewport) instead of O(n) |
| `message-list.tsx` | 50ms streaming throttle (`useThrottledMessages`) | Caps re-renders at 20fps during token streaming |
| `message-list.tsx` | `useMemo` for `groupMessages` computation | Groups recomputed only when messages array changes |
| `frontend/src/components/workspace/messages/markdown-content.tsx` | `useDeferredValue` for historical message content | React defers re-parse of stable messages while streaming is active |
| `frontend/src/app/workspace/layout.tsx` | TanStack Query `staleTime: 60s, gcTime: 10min` | Reduces redundant API fetches; keeps cache longer for faster navigation |

### Observability

```bash
# Check memory system health
curl http://127.0.0.1:19882/api/metrics/memory-health

# Check degradation level (normal / mild / heavy)
curl http://127.0.0.1:19882/api/metrics/memory-health | jq .degradation
```
