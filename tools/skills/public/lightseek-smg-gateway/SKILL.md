---
name: lightseek-smg-gateway
description: Model gateway routing skill for SMG-style experiments.
license: MIT
---
# lightseek-smg-gateway

Plan a routing experiment without replacing stable runtime: providers, auth, tenancy, fallback, tokenization cache, metrics, and rollback.

## OctoAgent usage

1. Confirm the user goal and constraints.
2. Load any matching plugin command with `get_plugin_command`.
3. Run `integrated_workflow_run` when a workflow ID is available.
4. Produce artifacts and review them against the quality gates before side effects.
