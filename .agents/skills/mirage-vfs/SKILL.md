---
name: mirage-vfs
description: Virtual filesystem planning skill for agent workspaces and task artifacts.
license: MIT
---
# mirage-vfs

Map user files, generated artifacts, memory snippets, and remote resources into a bounded VFS contract. Keep write paths explicit and reversible.

## OctoAgent usage

1. Confirm the user goal and constraints.
2. Load any matching plugin command with `get_plugin_command`.
3. Run `integrated_workflow_run` when a workflow ID is available.
4. Produce artifacts and review them against the quality gates before side effects.
