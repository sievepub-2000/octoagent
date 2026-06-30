---
name: peekaboo-vision-mcp
description: Screen capture and visual QA skill for MCP-backed observation workflows.
license: MIT
---
# peekaboo-vision-mcp

Resolve the platform capture backend, capture target, visual question, expected evidence, and fallback when a GUI is unavailable.

## OctoAgent usage

1. Confirm the user goal and constraints.
2. Load any matching plugin command with `get_plugin_command`.
3. Run `integrated_workflow_run` when a workflow ID is available.
4. Produce artifacts and review them against the quality gates before side effects.
