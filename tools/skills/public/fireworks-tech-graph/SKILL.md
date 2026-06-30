---
name: fireworks-tech-graph
description: Technical diagram generation skill for architecture and workflow visuals.
license: MIT
---
# fireworks-tech-graph

Convert prose into a diagram brief: subject, nodes, edges, layout, style, labels, and quality checks. Prefer SVG/PNG artifacts with readable text.

## OctoAgent usage

1. Confirm the user goal and constraints.
2. Load any matching plugin command with `get_plugin_command`.
3. Run `integrated_workflow_run` when a workflow ID is available.
4. Produce artifacts and review them against the quality gates before side effects.
