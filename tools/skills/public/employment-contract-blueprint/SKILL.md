---
name: employment-contract-blueprint
description: Jurisdiction-aware employment-contract clause blueprint: enumerates required clauses (probation, IP, non-compete, severance, notice, working hours, leave, confidentiality, dispute resolution) and emits a structured outline. NEVER produces binding contract text; attorney review is mandatory.
---

# Employment Contract Clause Blueprint

## Overview

This skill produces a **jurisdiction-aware clause blueprint** for an employment contract — NOT the contract itself. Output is a structured outline of required clause headings + bullet-point intents, plus an attorney-review checklist. A licensed attorney in the target jurisdiction MUST review and finalize any binding text.

## Safety Model

| Concern | Rule |
|---|---|
| Binding text | NEVER produced. Output is headings + intents only. |
| Disclaimer | Every artifact starts with the non-legal-advice disclaimer. |
| Jurisdiction | Required. Multi-jurisdiction is opt-in only. |
| Attorney review | Mandatory before any party signs. |
| Refusal | Asking for finalized contract text triggers refusal. |


## Required Inputs

1. `jurisdiction` (country and where relevant state/province; refuse if missing)
2. `role` and `employment_type` (full_time/part_time/contract/intern)
3. `term` (indefinite or fixed N months)
4. `industry` (drives clause emphasis: e.g. tech IP, healthcare data)
5. `special_concerns` (remote work, cross-border, regulated profession)

## Output Contract

- `contract_clause_blueprint.md` (markdown, required)
- `jurisdiction_compliance_matrix.json` (json, required)
- `attorney_review_checklist.md` (markdown, required)

## Workflow Steps

1. **intake** — collect jurisdiction, role, employment_type (full_time/part_time/contract/intern), term (indefinite/fixed N months), industry, special concerns (remote, multi-jurisdiction). Refuse if jurisdiction is missing.
2. **jurisdiction_lock** — lock the target jurisdiction; refuse to mix clauses across jurisdictions unless user explicitly opts in for a multi-jurisdiction summary
3. **clause_taxonomy** — enumerate the standard clause headings expected in the chosen jurisdiction (probation, IP_assignment, non_compete, non_solicitation, severance, notice_period, working_hours, leave, confidentiality, data_protection, dispute_resolution, termination_for_cause, termination_without_cause); for each emit applicability + region-specific note (e.g. CA non-compete generally unenforceable; CN probation cap by contract term; EU GDPR data clauses)
4. **blueprint_render** — render the clause blueprint as headings + bullet-point intents (NOT contract text); each clause carries a `requires_attorney_drafting: true` flag
5. **attorney_review_gate** — emit an explicit attorney-review checklist artifact listing each clause, jurisdiction note, and required external review item before any text is finalized
6. **legal_safety** — confirm output is a blueprint, not a contract; refuse if user asks to produce finalized binding contract text

## Refusal Cases

- User asks for finalized binding contract text — refuse; output is blueprint only.
- `jurisdiction` missing — refuse.
- User asks to mix multiple jurisdictions silently — refuse; require explicit opt-in for a multi-jurisdiction *summary*.
- Regulated profession (medical, legal, securities) without confirmation that licensing is owned elsewhere — refuse.
