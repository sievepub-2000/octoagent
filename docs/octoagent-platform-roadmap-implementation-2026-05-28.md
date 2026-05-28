# OctoAgent Platform Enhancements - 2026-05-28

This change implements the next hardening layer for OctoAgent after the initial MCP/tool cleanup.

## MCP Acceptance Standard

Every configured MCP now has a `smokeTest` block and must pass schema validation, startup, `list_tools`, minimal invocation, registry display, and graceful degradation checks. Smoke results are stored at `runtime/cache/mcp_smoke.json` and exposed through `/api/mcp/smoke`.

## MCP Inventory

Enabled and smoke-tested MCP servers:

- `filesystem`
- `postgres`
- `http-api`
- `openapi` (`@ivotoby/openapi-mcp-server`)
- `docker-compose` (local FastMCP compose inspector)
- `redis` (`@modelcontextprotocol/server-redis`)
- `kubernetes` (`mcp-server-kubernetes`, using a smoke kubeconfig until a real cluster kubeconfig is supplied)
- `docker` (`docker-mcp`)

The npm MCP packages are installed under `runtime/tools/mcp`; package metadata is committed while dependency payloads remain local runtime state.

## Builtin Tool Manifest

`/api/tools/registry` now includes machine-readable builtin metadata: parameters, permission scope, timeout hint, output artifact hint, risk level, and failure modes.

## WebUI

The Tools Hub shows MCP/tool status, failure reasons, risk labels, parameter counts, timeout hints, and artifact presence.

## Awesome Selfhosted Catalog

`awesome_selfhosted` now reads `runtime/catalogs/awesome-selfhosted-saas.json`. Entries include tags, rating, deployment complexity, and task templates for SaaS creation, auth, billing, compose deployment, and security baseline checks.

## Eval and Agent Loop

Task-level eval definitions live in `backend/src/harness/evaluation/octoagent_eval_matrix.json`. The repo-level loop is documented in `docs/octoagent-eval-and-agent-loop-2026-05-28.md`.
