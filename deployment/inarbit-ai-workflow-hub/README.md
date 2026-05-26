# Inarbit AI Workflow Hub

Lightweight production control-plane entry for `inarbit.work`.

This package intentionally excludes bulk registration, SMS verification brokerage,
quota-pool sharing, provider-limit evasion, and public multi-account token proxy
features. External projects such as CPA-Dashboard, Antigravity-Manager, Team
helpers, and Admin Web are represented as governed connectors or references until
their usage is reviewed for provider terms, data handling, and production security.

## Runtime

- Binds to `127.0.0.1:8095`
- Exposes `/health`
- Exposes `/api/status`
- Intended public path behind Nginx: `/ai-ops/`

## Deploy

Use the local deploy script from the repository root:

```bash
./deployment/inarbit-ai-workflow-hub/deploy.sh inarbit
```
