# Inarbit AI Workflow Deployment Report

Date: 2026-04-30
Host: `inarbit-prod`
Public IP: `136.109.140.114`
Public URL: `https://inarbit.work/ai-ops/`

## Deployment Summary

Deployed `Inarbit AI Workflow Hub` as a lightweight production control plane on
`inarbit.work`. The hub provides a unified status page and JSON status API for
existing production services and planned AI account/workflow governance
connectors.

This deployment is configured for authenticated research and testing. Bulk
registration, SMS verification brokerage, quota-pool sharing, and public
multi-account token proxy workflows are not exposed.

## Host Assessment

- OS: Ubuntu 22.04 on Linux `6.8.0-1052-gcp`
- Architecture: `x86_64`
- CPU: 2 vCPU, Intel Xeon 2.20 GHz
- Memory: 3.8 GiB total, about 2.2 GiB available at deployment time
- Swap: 4.0 GiB total, about 802 MiB used at deployment time
- Disk: 49 GiB root volume, 38 GiB used, 11 GiB available
- Existing edge: Nginx `1.18.0`
- Existing runtime: Node `v22.22.1`, Python `3.10.12`, Redis on `127.0.0.1:6379`

The host is suitable for a lightweight control plane and connector registry.
It is not suitable for running every referenced upstream project as a full
production stack at the same time without upgrading disk and memory.

## Deployed Components

- Systemd service: `ai-workflow-hub.service`
- Runtime path: `/opt/ai-workflow-hub`
- Local bind: `127.0.0.1:8095`
- Nginx public route: `/ai-ops/`
- Health endpoint: `/ai-ops/health`
- Status endpoint: `/ai-ops/api/status`

## Integrated Runtime Systems

- `redis`: active local data dependency, private only
- `Unified Access Control`: active authentication, RBAC, and audit gate.
- `CPA-Dashboard`: active internal gateway panel at `https://gateway.inarbit.work/`
- `ChatGPT Admin Web Chat`: active deployment at `https://chat.inarbit.work/`
- `ChatGPT Admin Web Dashboard`: active deployment at `https://admin.inarbit.work/`

## Removed Components

- `n8n.service`: stopped, disabled, service file removed, app/data directories removed.
- `inarbit-whisper.service`: stopped, disabled, service file removed, app/model/temp/log directories removed.
- `leadops-api.service`: stopped, disabled, service file removed, drop-in credentials removed,
  environment files removed, app directory removed, legacy app frontend removed, and all `8091`
  Nginx routes removed.
- Removed public Nginx routes for `/n8n/` and the legacy Whisper `/api/` route from the services site.
- Verified no remaining `n8n` or `whisper` app/data/service paths and no listeners on `5678` or `8090`.
- Verified no remaining LeadOps service/app/env paths and no listener on `8091`.

## Research and Test Integration Scope

- `CPA-Dashboard`: deployed as the internal gateway panel for owned credentials
  and gateway testing. Quota pooling and public dispatch remain disabled.
- `Antigravity-Manager`: protocol compatibility component for authenticated
  research and testing with owned credentials.
- `team-manage` / `chatgpt-team-helper`: represented as `Team Entitlement
  Connector` for legitimate seat assignment, approval, and audit.
- `ChatGPT-Admin-Web`: chat and dashboard apps are deployed. The upstream README
  still states that the admin/backend area is under development, so selected
  admin APIs are handled by the hub for stability.
- `Cli-Proxy-API-Management-Center`: enabled as a gateway test slot.
  Public reverse proxy, multi-account dispatch, quota pooling, and provider
  limit evasion remain disabled.
- `chatgpt_register`: enabled as a manual import placeholder. Bulk registration,
  SMS brokerage, and automatic replenishment workflows are not deployed.

## Workflow Model

1. Intake: `gateway.inarbit.work` or approved external forms accept approved requests.
2. Approval: AI Workflow Hub classifies sensitive operations and routes risky
   actions to manual approval.
3. Execution: OctoAgent or the legal gateway executes approved tasks through
   owned APIs, legal gateway credentials, or self-hosted models.
4. Audit: AI Workflow Hub records system, tool, model, connector, and outcome
   metadata without storing raw secrets.

## Unified Access Control

- Added unified login at `https://inarbit.work/ai-ops/login`.
- Added signed session cookies scoped to `.inarbit.work`, so one login covers
  `gateway.inarbit.work`, `chat.inarbit.work`, `admin.inarbit.work`, and
  `inarbit.work/ai-ops/`.
- Added RBAC levels:
  - `viewer`: chat access.
  - `operator`: gateway and ai-ops access.
  - `admin`: admin dashboard access.
- Generated the initial admin credential on the remote host only:
  `/root/ai-workflow-admin-credentials.txt`.
- Added application audit log:
  `/var/log/ai-workflow-hub/audit.jsonl`.
- Added Nginx access audit log:
  `/var/log/nginx/ai_access_audit.log`.

## Admin Credential Alignment

Updated on 2026-05-05:

- Unified Access Control accepts the requested administrator username and
  password. The password is stored only in the remote host auth config/hash and
  is not committed to the repository.
- `CPA-Dashboard` has no separate native username/password in the deployed
  application; access is controlled by the unified Nginx auth gate.
- `ChatGPT Admin Web Chat` accepts the same administrator credential through
  its internal login endpoint.
- `ChatGPT Admin Web Dashboard` accepts the same administrator credential
  through the hub-backed dashboard login endpoint.
- Dashboard management APIs for `/api/analyze/*`, `/api/user`, `/api/order`,
  and `/api/plan` are routed through the hub to avoid the upstream Next.js
  middleware/API instability observed on the current host runtime.

## Verification

- `python3 -m py_compile deployment/inarbit-ai-workflow-hub/server.py`: passed.
- `nginx -t` on `inarbit-prod`: passed.
- `systemctl is-active ai-workflow-hub.service`: `active`.
- Local health on host: `http://127.0.0.1:8095/health` returned `OK`.
- Public health: `https://inarbit.work/ai-ops/health` returned `OK`.
- Public status JSON returned active statuses for Unified Access Control, Redis,
  CPA-Dashboard, ChatGPT Admin Web Dashboard, and ChatGPT Admin Web Chat.
- Chromium headless rendered `https://inarbit.work/ai-ops/` and confirmed
  visible entries for CPA-Dashboard, Cli-Proxy API Management Center, and
  `chatgpt_register`.

## Follow-up Verification After Cleanup

- `n8n.service` and `inarbit-whisper.service`: `inactive`.
- Remaining removed paths check: no `/opt/n8n`, `/opt/inarbit-whisper`,
  `/var/lib/n8n`, `/home/node/.n8n`, removed service files, or quarantine
  directories.
- Remaining ports check: no listeners on `5678` or `8090`.
- Removed residual n8n user/group, global n8n command, root n8n logs,
  temporary export/upload directories, old backup env files, and local rollback
  helper scripts.
- Active services: `cpa-dashboard.service`, `chatgpt-admin-chat.service`,
  `chatgpt-admin-dash.service`, and `ai-workflow-hub.service`.
- Public HTTPS routes:
  - `https://gateway.inarbit.work/`: `200 OK`, CPA-Dashboard page rendered.
  - `https://chat.inarbit.work/`: `200 OK`, ChatGPT Admin Web chat page rendered.
  - `https://admin.inarbit.work/`: `200 OK`, ChatGPT Admin Web dashboard login rendered.
- Certbot system binary is currently broken by global Python package pollution;
  `/opt/certbot-venv/bin/certbot` worked and issued the HTTPS certificate for
  `gateway.inarbit.work`, `chat.inarbit.work`, and `admin.inarbit.work`.
- Chromium headless rendered all three public panels and the updated AI Workflow
  Hub successfully.
- Unauthenticated requests to `gateway`, `chat`, `admin`, and `ai-ops` returned
  `302` to the unified login page.
- Authenticated admin requests returned:
  - `https://gateway.inarbit.work/`: `200`.
  - `https://chat.inarbit.work/`: `200`.
  - `https://admin.inarbit.work/`: `200`.
  - `https://inarbit.work/ai-ops/api/status`: `200`.
  - `https://gateway.inarbit.work/api/config`: `200`.
  - `https://gateway.inarbit.work/api/service/status`: `200`.
- CPA-Dashboard currently reports the legal gateway service as `configured=false`
  because the legal gateway binary/config has not been installed under
  `/opt/legal-gateway` yet. The protected panel and API path are ready for that
  gateway once configured.

## Follow-up Verification After Credential Alignment

Verified on 2026-05-05:

- `python3 -m py_compile deployment/inarbit-ai-workflow-hub/server.py`: passed.
- `bash -n deployment/inarbit-ai-workflow-hub/deploy.sh`: passed.
- `nginx -t` on `inarbit-prod`: passed.
- Active services: `ai-workflow-hub.service`, `cpa-dashboard.service`,
  `chatgpt-admin-chat.service`, `chatgpt-admin-dash.service`, and `nginx`.
- Unified login returned an authenticated admin session for
  `/ai-ops/auth/whoami`.
- Authenticated page checks returned `200` for:
  `https://inarbit.work/ai-ops/`, `https://gateway.inarbit.work/`,
  `https://chat.inarbit.work/`, and `https://admin.inarbit.work/`.
- `ChatGPT Admin Web Chat` internal login returned a session token, and
  `/api/user/info` returned the admin profile when called with the upstream
  expected raw `Authorization` token header.
- `ChatGPT Admin Web Dashboard` login returned a session token, and the
  hub-backed dashboard APIs returned `200` for `/api/analyze/monthly`,
  `/api/user`, `/api/order`, and `/api/plan`.
- Audit records were written for unified login, auth allow decisions, dashboard
  login, and dashboard API reads.

## Remaining Work

- Move connector approvals and audit records into a durable store.
- Add Prometheus or journald-based alerting for failed dependencies.
- Upgrade disk or move heavier systems to a larger worker host before running
  additional Node/FastAPI stacks.
- Implement a compliant model gateway using owned API keys and self-hosted
  models, with RBAC, rate limits, audit records, and secret redaction.
