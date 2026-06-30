---
name: witr-runtime-diagnosis
description: Runtime diagnosis skill for explaining why processes and services are running.
license: MIT
---
# witr-runtime-diagnosis

Collect process, service, port, parent, and config evidence; explain ownership and whether action is needed.

## OctoAgent usage

1. Confirm the user goal and constraints.
2. Load any matching plugin command with `get_plugin_command`.
3. Run `integrated_workflow_run` when a workflow ID is available.
4. Produce artifacts and review them against the quality gates before side effects.
