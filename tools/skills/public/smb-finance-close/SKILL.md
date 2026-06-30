---
name: smb-finance-close
description: Plan-only SMB month-end close playbook: bank recon, accruals, revenue cutoff, expense classification, tax provision check, close packet, audit trail review.
---

# SMB Month-End Finance Close

## Overview

This skill produces a **plan-only month-end finance close** for SMB teams. Output is a structured Markdown + JSON draft for the responsible owner to review; OctoAgent does not mutate any external system.

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

- `close_checklist.md` (markdown, required)
- `reconciliation_matrix.json` (json, required)
- `audit_trail.json` (json, required)

## Workflow Steps

1. **intake** — collect required month-end close inputs and refuse to proceed when scope is undefined
2. **bank_recon_plan** — produce the bank recon section with explicit owners, due dates, and acceptance criteria
3. **accruals_plan** — produce the accruals section with explicit owners, due dates, and acceptance criteria
4. **revenue_recognition_cutoff_plan** — produce the revenue recognition cutoff section with explicit owners, due dates, and acceptance criteria
5. **expense_classification_plan** — produce the expense classification section with explicit owners, due dates, and acceptance criteria
6. **tax_provision_check_plan** — produce the tax provision check section with explicit owners, due dates, and acceptance criteria
7. **close_packet_plan** — produce the close packet section with explicit owners, due dates, and acceptance criteria
8. **audit_trail_review_plan** — produce the audit trail review section with explicit owners, due dates, and acceptance criteria
9. **quality_gate** — validate completeness, owner coverage, and acceptance criteria; refuse to finalize until gaps are addressed
10. **draft_only_safety** — confirm no external systems are mutated; all outputs are reviewable Markdown/JSON drafts for the responsible team

## Refusal Cases

- User asks OctoAgent to push to an external system — refuse; draft only.
- Scope undefined — ask before planning.
