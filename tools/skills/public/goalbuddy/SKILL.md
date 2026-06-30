---
name: goalbuddy
description: Goal contract skill for bounded autonomous agent work.
license: MIT
---
# goalbuddy

Turn broad requests into objective, constraints, acceptance checks, risks, tool plan, and stop conditions before execution.

## OctoAgent usage

1. Confirm the user goal and constraints.
2. Load any matching plugin command with `get_plugin_command`.
3. Run `integrated_workflow_run` when a workflow ID is available.
4. Produce artifacts and review them against the quality gates before side effects.
