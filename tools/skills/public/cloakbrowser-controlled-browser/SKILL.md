---
name: cloakbrowser-controlled-browser
description: Default browser tool for general web automation without explicit authorization required.
license: MIT
---
# cloakbrowser-controlled-browser

Use only for explicitly authorized browsing/testing. State target, permission, data boundary, standard-browser fallback, and side-effect guardrails.

## OctoAgent usage

1. Confirm the user goal and constraints.
2. Load any matching plugin command with `get_plugin_command`.
3. Run `integrated_workflow_run` when a workflow ID is available.
4. Produce artifacts and review them against the quality gates before side effects.
