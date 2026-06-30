---
name: photo-agents
description: Vision-grounded workflow skill with layered memory and self-written skills.
license: MIT
---
# photo-agents

For visual/computer operation tasks, separate observation, memory, action, verification, and learned skill capture.

## OctoAgent usage

1. Confirm the user goal and constraints.
2. Load any matching plugin command with `get_plugin_command`.
3. Run `integrated_workflow_run` when a workflow ID is available.
4. Produce artifacts and review them against the quality gates before side effects.
