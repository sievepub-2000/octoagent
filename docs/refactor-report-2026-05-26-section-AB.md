# Refactor report — Section A/B drift cleanup (2026-05-26)

Scope: continuation of the gateway router refactor stream, addressing the
99 Section A (backend orphans) and 6 Section B (frontend orphans) entries
produced by the v2 prefix-aware drift audit.

## Outcome

| Metric | Before | After | Δ |
|---|---|---|---|
| Section A — unreachable backend routes | 99 | 85 | **-14** |
| Section B — unmatched frontend URLs | 6 | **0** | -6 |
| Section C — matched pairs | 214 | 214 | 0 |
| Router files | 45 | 41 | -4 |
| Backend pytest | 291 pass | 291 pass | 0 |
| Frontend `tsc --noEmit` | clean | clean | 0 |
| Gateway smoke (`/api/runtime/doctor`) | 200 | 200 | 0 |

## What changed

### 1. Whole-file router deletions (commit `e449d1b`)

| Router | Routes removed | Rationale |
|---|---|---|
| `integrations.py` | 1 | sole endpoint `GET /api/integrations/capabilities`; zero callers in repo |
| `runtime_identity.py` | 1 | sole endpoint `GET /api/runtime/identity`; runtime identity package is still used directly |
| `evaluation.py`  | 4 | `/evaluation/*` (no `/api` prefix), entirely unreached; tagged as orphan in 2026-05-26 evaluation report |
| `public_runtime.py` | 5 | `/api/runtime/workflows/{task_id}*`; redundant with `task_workspaces.py` `studio-runtime` exits |

Also removed their imports + registrations from `router_registry.py` and
`routers/__init__.py`.

### 2. Surgical endpoint removals (commit `210a1c2`)

| Router | Endpoint | Rationale |
|---|---|---|
| `brain.py` | `GET /api/brain/capabilities` | decorative status; brain plan endpoint untouched |
| `research_runtime.py` | `GET /api/research-runtime/status` | decorative; capabilities/programs/experiments retained |
| `browser_runtime.py` | `GET /api/browser-runtime/status` | decorative; sessions surface retained |

### 3. Audit tool hardening (commit `210a1c2`)

`scripts/dev_tools/api_drift_audit.py` gained two extra match passes:

1. **Prefix tolerance** — a frontend URL is counted as matched if it is a
   strict path prefix of any backend full path. Fixes false positives for
   base-URL constants such as `'/api/execution-nodes'`,
   `'/api/runtime/rag-config'`, `'/api/tenants'`.
2. **Frontend-side regex** — a frontend URL with `{x}` placeholders is
   counted as matched if its compiled regex matches any backend full path.
   Fixes false positives where the frontend templates a segment that is a
   literal in the backend, e.g. `/api/task-workspaces/{x}/{x}` matching
   `/api/task-workspaces/{task_id}/studio-runtime`.

Net effect: Section B went from 6 to 0 with no underlying frontend changes.

### 4. Studio runtime contract consolidation

The `studio_runtime.py` router (deleted in `1512c37`) and `public_runtime.py`
(deleted here) were two parallel exits for the workflow runtime contract.
After this round the single canonical surface is:

- `GET  /api/task-workspaces/{task_id}/studio-runtime`
- `GET  /api/task-workspaces/{task_id}/studio-runtime/events`

defined in `task_workspaces.py`. The orphaned `get_public_runtime*` methods
on `WorkflowCoreService` remain (one still has an internal caller and a
test); a follow-up should prune those once the test is reframed.

## Remaining Section A (85 endpoints)

See [docs/api_drift_secA_ownership.md](api_drift_secA_ownership.md) for
the per-endpoint table.

| Disposition | Count | Action |
|---|---|---|
| `DEAD-CONFIRMED` | 3 | safe to remove pending PM/ops sign-off |
| `NEEDS-OPS` | 22 | admin / operator surfaces in routers like `memory`, `hooks`, `software_interfaces`, `distributed_execution`, `multi_tenant`, `model_auth`, `mcp`, `skill_evolution`, `query_engine`, `capabilities`, `metrics` — currently no in-repo reference but each is a documented operator API; requires PM/ops confirmation before deletion |
| `REF-INTERNAL` | 60 | referenced from backend code, tests, or docs; not consumed by the current frontend bundle but still in active use elsewhere — no action |

The `NEEDS-OPS` cohort is the right place to engage product / ops; this
report does not unilaterally remove them.

## Commits

- `1512c37` — drop studio_runtime.py + ship v2 drift audit
- `e449d1b` — drop 4 dead routers (11 unreachable routes)
- `210a1c2` — surgical drop 3 decorative status routes + audit prefix tolerance

