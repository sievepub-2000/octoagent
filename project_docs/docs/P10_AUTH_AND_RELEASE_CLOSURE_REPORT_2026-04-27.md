# P10 Auth And Release Closure Report - 2026-04-27

## Scope Added To Task List

- Built-in registration/login page at `/auth/register`.
- Registration requires username, password, email, and an 8-digit email verification code valid for 10 minutes.
- First login uses username and password; subsequent login can use the trusted terminal fingerprint.
- New terminal verification uses the registered email before trusting that fingerprint.
- User account details are stored in OctoAgent runtime SQLite at `workspace/runtime/octoagent_users.db`.
- Authenticated sessions propagate `X-OctoAgent-Session-Token` and tenant context through the existing frontend API client.
- The new account store binds each registered user to a tenant in the existing multi-tenant registry.
- Plugin registry writes now use per-process temporary files to avoid parallel soak startup races on `registry.tmp`.

## Implementation Summary

### Backend

- Added `backend/src/user_accounts/` as the internal account store.
- Added `backend/src/gateway/routers/auth.py` with `/api/auth/*` endpoints:
  - `POST /api/auth/register/start`
  - `POST /api/auth/register/verify`
  - `POST /api/auth/login`
  - `POST /api/auth/device-login`
  - `POST /api/auth/device/verify/start`
  - `POST /api/auth/device/verify`
  - `GET /api/auth/me`
- Registered the auth router in `backend/src/gateway/router_registry.py`.
- Email delivery uses SMTP when configured through `OCTO_SMTP_*`; without SMTP, codes are logged for local development only.
- Passwords and verification codes are PBKDF2-hashed; device fingerprints and session tokens are hashed before storage.

### Frontend

- Added `frontend/src/app/auth/register/page.tsx` as a minimal auth entry.
- Added `frontend/src/core/auth/api.ts` and `frontend/src/core/auth/device.ts`.
- Updated `frontend/src/core/api/http.ts` to attach session and tenant headers from local storage.
- Kept the existing workspace UI intact; no new management workspace was added.

### DevOps And Docs

- Routed `/api/auth/*` through Gateway in nginx local and Docker templates.
- Updated module/router inventory to 45 backend top-level modules, 38 registered router groups, and 41 router files.
- Documented the auth page, auth API, SMTP variables, and runtime user DB path.

## Validation Evidence

- Backend compile: passed for `user_accounts`, auth router, and router registry.
- Ruff: passed for changed backend auth/router files.
- Frontend typecheck: `pnpm run typecheck` passed.
- Core auth store smoke: registration, registration-code verification, password login, trusted-device login, and new-device email verification passed.
- 19880 route checks: `/auth/register`, `/health`, and `/api/models` returned HTTP 200.
- Auth API through nginx: `/api/auth/login`, `/api/auth/me`, and `/api/auth/device-login` returned HTTP 200.
- Real WebUI smoke: passed, including first chat message, multi-turn message, continuation route, workspace settings, bootstrap section, and task workspace cleanup.
- Short long-running soak smoke after plugin registry race fix: passed with active runs, worker queue, and checkpoints settled.

## Current System Assessment

### Frontend/WebUI

Status: release candidate. The current Next.js UI is functional and smoke-tested through the unified 19880 entry. The new auth page is intentionally narrow and does not expand the workspace surface. Remaining risk is deeper E2E coverage for abnormal auth states, expired codes, changed fingerprints, and full logout/session expiry behavior.

### Gateway API

Status: broad but healthy. The gateway now has 38 registered router groups and 41 router files. Health, models, auth, tenant, distributed execution, and runtime checks are reachable through the unified ingress. The router surface is still large; production hardening should continue moving shared authorization into a common dependency or middleware.

### LangGraph Runtime

Status: operational. Provider contract and WebUI smoke are passing. Stale active run cleanup has been added, but long soak reports should remain a release gate because active-run settling is the main historical long-duration risk.

### Models/Embedding

Status: recovered. SentenceTransformerBackend is active with 384-dimensional embeddings, and startup scripts pin cache/offline behavior to reduce user-switch cache drift. Continue monitoring first-start cache misses after server restarts.

### Memory/Query

Status: usable with monitoring. Memory health and query maintenance endpoints are available. The priority for launch is sustained memory plateau behavior under long conversations rather than adding more retrieval features.

### Distributed Execution

Status: improved security posture. Worker token support, lease/callback/failover replay, and smoke coverage are in place. Production must set `OCTO_EXECUTION_WORKER_TOKEN`.

### Multi Tenant

Status: integrated with auth. Registered users get tenant binding through the account store. Tenant write/export operations already require operator/admin constraints. Production must set `OCTO_OPERATOR_TOKEN`.

### Operator Governance

Status: functional with one mandatory production setting. Audit redaction/signing and role/token helpers exist. Production must set `OCTO_OPERATOR_AUDIT_SECRET`; otherwise signatures remain checksum-level, not strong audit authentication.

### Skills/Tools Hub

Status: stable enough for release candidate. Registration smoke has passed. The generated `.github/copilot-instructions.md` behavior should remain CI-owned or explicitly documented to avoid accidental local churn.

### Docs/DevOps

Status: aligned to current code. Port layout, router counts, module counts, auth route, and SMTP settings are documented. The canonical root remains `/home/sieve-pub/public-workspace/octoagent`.

## Remaining Release Risks

- Long soak reports still need final review after the active 2h/8h/24h runs finish.
- SMTP is not configured in the checked environment; production must configure SMTP before exposing registration.
- Global API auth enforcement is not enabled by default in this patch to avoid breaking existing operational and smoke flows at the end of release hardening. The session header path is now ready for a final middleware switch if strict access control is required.
- Local `.env` contains sensitive-looking configuration and must stay untracked; rotate any secrets that were ever exposed outside the host.

## Deferred Architecture Options

| Item | Recommendation | Value | Rationale |
| --- | --- | ---: | --- |
| Vue3 UI rewrite | Defer | 2/5 | A rewrite near launch has high regression risk. Current Next.js smoke is passing; optimize bundle, route splitting, memoization, and data cache first. Revisit only after profiling proves React/Next is the limiting factor. |
| Deep memory/resource optimization | Do in staged hardening | 5/5 | This directly protects long conversations and soak stability. Add memory budgets, leak checks, heap/SQLite/DuckDB trend reports, active-run cleanup gates, and compaction policy tests. |
| xray-core proxy layer | Conditional defer | 2/5 | Useful only if the product needs advanced egress routing, proxy protocol support, or regional failover. It adds operational and security complexity and will not automatically improve app latency. |
| Background generic agent | Pilot with strict guardrails | 4/5 | Valuable for silent conversation compression, long-term memory extraction, maintenance suggestions, and cleanup. It must be low privilege, quota-bound, auditable, cancellable, and never modify production config without approval. |
| public-apis/browser wing/superpowers/agent ui/openrelay/agent browser | Selective integration later | 3/5 | Integrate only where a current workflow has a clear gap. Prioritize browser/agent UI primitives already close to the product; avoid broad plugin sprawl before launch. |

## Deployment Recommendation

Proceed as a release candidate after committing and pushing this patch, provided the long soak reports are reviewed and production secrets are set. Do not start a Vue rewrite or proxy-layer replacement before this release. The highest-value next hardening item is memory plateau validation plus a strict auth middleware decision.
