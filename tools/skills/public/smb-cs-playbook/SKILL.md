---
name: smb-cs-playbook
description: Plan-only SMB customer-success playbook: kickoff agenda, 30/60/90 health-check templates, escalation paths, QBR template, churn-save runbook.
---

# SMB Customer Success Playbook

## Overview

This skill produces a **plan-only customer success playbook** for SMB teams. Output is a structured Markdown + JSON draft for the responsible owner to review; OctoAgent does not mutate any external system.

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

- `cs_playbook.md` (markdown, required)
- `health_score_matrix.json` (json, required)
- `escalation_runbook.md` (markdown, required)

## Workflow Steps

1. **intake** — collect required customer success inputs and refuse to proceed when scope is undefined
2. **kickoff_plan** — produce the kickoff section with explicit owners, due dates, and acceptance criteria
3. **d30_health_check_plan** — produce the d30 health check section with explicit owners, due dates, and acceptance criteria
4. **d60_health_check_plan** — produce the d60 health check section with explicit owners, due dates, and acceptance criteria
5. **d90_health_check_plan** — produce the d90 health check section with explicit owners, due dates, and acceptance criteria
6. **escalation_paths_plan** — produce the escalation paths section with explicit owners, due dates, and acceptance criteria
7. **qbr_template_plan** — produce the qbr template section with explicit owners, due dates, and acceptance criteria
8. **churn_save_runbook_plan** — produce the churn save runbook section with explicit owners, due dates, and acceptance criteria
9. **quality_gate** — validate completeness, owner coverage, and acceptance criteria; refuse to finalize until gaps are addressed
10. **draft_only_safety** — confirm no external systems are mutated; all outputs are reviewable Markdown/JSON drafts for the responsible team

## Refusal Cases

- User asks OctoAgent to push to an external system — refuse; draft only.
- Scope undefined — ask before planning.
