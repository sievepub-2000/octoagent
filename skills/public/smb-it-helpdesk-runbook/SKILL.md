---
name: smb-it-helpdesk-runbook
description: Plan-only SMB IT helpdesk runbook: ticket triage, priority matrix, password reset SOP, equipment request SOP, access request SOP, escalation paths, SLA definitions.
---

# SMB IT Helpdesk Runbook

## Overview

This skill produces a **plan-only it helpdesk runbook** for SMB teams. Output is a structured Markdown + JSON draft for the responsible owner to review; OctoAgent does not mutate any external system.

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

- `helpdesk_runbook.md` (markdown, required)
- `sla_matrix.json` (json, required)
- `triage_decision_tree.md` (markdown, required)

## Workflow Steps

1. **intake** — collect required IT helpdesk inputs and refuse to proceed when scope is undefined
2. **ticket_triage_plan** — produce the ticket triage section with explicit owners, due dates, and acceptance criteria
3. **priority_matrix_plan** — produce the priority matrix section with explicit owners, due dates, and acceptance criteria
4. **password_reset_sop_plan** — produce the password reset sop section with explicit owners, due dates, and acceptance criteria
5. **equipment_request_sop_plan** — produce the equipment request sop section with explicit owners, due dates, and acceptance criteria
6. **access_request_sop_plan** — produce the access request sop section with explicit owners, due dates, and acceptance criteria
7. **escalation_paths_plan** — produce the escalation paths section with explicit owners, due dates, and acceptance criteria
8. **sla_definitions_plan** — produce the sla definitions section with explicit owners, due dates, and acceptance criteria
9. **quality_gate** — validate completeness, owner coverage, and acceptance criteria; refuse to finalize until gaps are addressed
10. **draft_only_safety** — confirm no external systems are mutated; all outputs are reviewable Markdown/JSON drafts for the responsible team

## Refusal Cases

- User asks OctoAgent to push to an external system — refuse; draft only.
- Scope undefined — ask before planning.
