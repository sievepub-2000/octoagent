# Port Baseline

This document defines the default local ports used by OctoAgent.

The baseline can be remapped for a public/local ingress by overriding `OCTO_NGINX_PORT` together with `OCTO_PUBLIC_BASE_URL` before starting the stack.

## Default Ports

| Port | Service | Scope | Notes |
| ------ | ------ | ------ | ------ |
| `19884` | LangGraph | Local / Docker internal | Agent runtime and streaming API |
| `19886` | Frontend | Local / Docker internal | Next.js UI |
| `19882` | Gateway | Local / Docker internal | REST API surface |
| `19888` | Provisioner | Docker internal | Optional K8s sandbox provisioner |
| `19880` | Nginx | Local / Docker published | Unified entry point |
| `19900` | Sandbox base port | Local runtime allocation | Starting host port for AIO sandbox containers |

## Default Access Paths

- Unified app: `http://localhost:19880`
- Unified API: `http://localhost:19880/api/*`
- Unified LangGraph: `http://localhost:19880/api/langgraph/*`
- Built-in auth page: `http://localhost:19880/auth/register`
- Built-in auth API: `http://localhost:19880/api/auth/*`
- Direct LangGraph: `http://localhost:19884`
- Direct Frontend: `http://localhost:19886`
- Direct Gateway: `http://localhost:19882`
- Provisioner: `http://localhost:19888`

## Runtime Rules

- Local `make dev` and `make start` use the same default port layout.
- Docker development uses the same port layout, with Nginx published on `19880`.
- External/local public ingress can be moved by exporting both `OCTO_NGINX_PORT` and `OCTO_PUBLIC_BASE_URL`.
- The sandbox allocator starts searching from `19900`.
- Kubernetes `NodePort` values for provisioned sandboxes are dynamic and are not part of the OctoAgent fixed default port set.

## Public Ingress Override Example

```bash
OCTO_NGINX_PORT=11980 \
OCTO_PUBLIC_BASE_URL=http://192.168.110.2:11980 \
make dev-daemon
```

This keeps the internal frontend/gateway/LangGraph ports unchanged while moving the unified ingress and auth-facing public base URL to `11980`.


## Production Security Environment

Before publishing the unified ingress, configure operator and worker secrets in the service environment:

```bash
OCTO_OPERATOR_TOKEN=<hex-or-base64-secret>
OCTO_EXECUTION_WORKER_TOKEN=<hex-or-base64-secret>
OCTO_OPERATOR_AUDIT_SECRET=<hex-or-base64-secret>
OCTO_RUNTIME_MAX_RUNNING_RUN_AGE_SECONDS=3600
```

These settings keep the existing local development flow intact while making governance writes, distributed execution callbacks, and audit signatures production-ready.

## Primary Source Files

- Shared local port baseline: [scripts/port-layout.sh](../../scripts/port-layout.sh)
- Local launcher: [scripts/serve.sh](../../scripts/serve.sh)
- Daemon launcher: [scripts/start-daemon.sh](../../scripts/start-daemon.sh)
- Local nginx template: [docker/nginx/nginx.local.conf.template](../../docker/nginx/nginx.local.conf.template)
- Docker compose: [docker/docker-compose-dev.yaml](../../docker/docker-compose-dev.yaml)
- Gateway defaults: [backend/src/gateway/config.py](../../backend/src/gateway/config.py)
- Frontend defaults: [frontend/src/core/config/index.ts](../../frontend/src/core/config/index.ts)
- Sandbox allocator: [backend/src/utils/network.py](../../backend/src/utils/network.py)

## Synchronization Rule

The authoritative local runtime port baseline is established through [scripts/port-layout.sh](../../scripts/port-layout.sh), with the frontend and backend consuming synchronized environment-derived defaults and nginx consuming rendered/templates derived from the same variables.

## Verification

Typical local validation flow:

```bash
make dev
curl http://127.0.0.1:19880/health
./backend/.venv/bin/python backend/scripts/run_webui_smoke.py \
  --frontend-url http://127.0.0.1:19880 \
  --gateway-url http://127.0.0.1:19880
```
