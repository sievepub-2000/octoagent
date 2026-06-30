---
name: smb-sales-motion
description: Plan-only SMB sales motion playbook: ICP definition, outbound cadence, discovery script, demo template, proposal template, negotiation guardrails, CS handoff packet.
---

# SMB Sales Motion Playbook

## Overview

This skill produces a **plan-only sales motion playbook** for SMB teams. Output is a structured Markdown + JSON draft for the responsible owner to review; OctoAgent does not mutate any external system.

## Safety Model

| Concern | Rule |
|---|---|
| Side effects | NONE. Plan only. |
| Owner sign-off | Required before execution. |
| External system writes | Forbidden in this vertical (no CRM, no ERP, no ticketing mutation). |


## Required Inputs

1. `scope` — what slice of the playbook is being requested
2. `owner_team` — who reviews/executes
3. `timeline` — fiscal period or sprint window
4. Domain-specific fields as listed in the workflow steps

## Output Contract

- `sales_motion_playbook.md` (markdown, required)
- `deal_stage_definitions.json` (json, required)
- `handoff_packet.md` (markdown, required)

## Workflow Steps

1. **intake** — collect required sales motion inputs and refuse to proceed when scope is undefined
2. **icp_definition_plan** — produce the icp definition section with explicit owners, due dates, and acceptance criteria
3. **outbound_cadence_plan** — produce the outbound cadence section with explicit owners, due dates, and acceptance criteria
4. **discovery_script_plan** — produce the discovery script section with explicit owners, due dates, and acceptance criteria
5. **demo_template_plan** — produce the demo template section with explicit owners, due dates, and acceptance criteria
6. **proposal_template_plan** — produce the proposal template section with explicit owners, due dates, and acceptance criteria
7. **negotiation_guardrails_plan** — produce the negotiation guardrails section with explicit owners, due dates, and acceptance criteria
8. **handoff_to_cs_plan** — produce the handoff to cs section with explicit owners, due dates, and acceptance criteria
9. **quality_gate** — validate completeness, owner coverage, and acceptance criteria; refuse to finalize until gaps are addressed
10. **draft_only_safety** — confirm no external systems are mutated; all outputs are reviewable Markdown/JSON drafts for the responsible team

## Refusal Cases

- User asks OctoAgent to push to an external system — refuse; draft only.
- Scope undefined — ask before planning.
