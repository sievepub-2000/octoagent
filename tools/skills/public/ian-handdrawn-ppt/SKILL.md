---
name: ian-handdrawn-ppt
description: Chinese hand-drawn technical image deck skill for covers, pages, and contact sheets.
license: MIT
---
# ian-handdrawn-ppt

Intake Chinese or English source material, plan a 21:9 cover and 16:9 pages, keep visible Chinese text short, and output image prompts plus quality gates.

## OctoAgent usage

1. Confirm the user goal and constraints.
2. Load any matching plugin command with `get_plugin_command`.
3. Run `integrated_workflow_run` when a workflow ID is available.
4. Produce artifacts and review them against the quality gates before side effects.
