# Phase 8 — SMB Vertical Capabilities

**Status:** 11 verticals shipped across four families (HRIS brokers, IDP brokers, legal blueprint, SMB plan-only playbooks) on top of the original HR-onboarding pilot (`5f3a17c`).  
**Date:** 2026-05-26  
**Scope:** All verticals are **plan-only** or **signed-intent-only**. OctoAgent NEVER calls external systems directly. Any vendor API request is emitted as a structured envelope artifact for a credentialed operator to execute out-of-band.

## Vertical inventory

### Family A — SMB plan-only playbooks (4 verticals + 1 pilot)

| project_id | workflow_id | safety mode | artifacts |
|---|---|---|---|
| `smb-hr-onboarding` (pilot) | `smb-hr-onboarding-plan` | `plan_only` | onboarding_plan.md, equipment_provisioning.json, compliance_checklist.json |
| `smb-cs-playbook` | `smb-cs-playbook-plan` | `plan_only` | cs_playbook.md, health_score_matrix.json, escalation_runbook.md |
| `smb-finance-close` | `smb-finance-close-plan` | `plan_only` | close_checklist.md, reconciliation_matrix.json, audit_trail.json |
| `smb-sales-motion` | `smb-sales-motion-plan` | `plan_only` | sales_motion_playbook.md, deal_stage_definitions.json, handoff_packet.md |
| `smb-it-helpdesk-runbook` | `smb-it-helpdesk-runbook-plan` | `plan_only` | helpdesk_runbook.md, sla_matrix.json, triage_decision_tree.md |

### Family B — HRIS provisioning brokers (3 verticals, signed-intent-only)

| project_id | workflow_id | api_target.vendor | safety mode |
|---|---|---|---|
| `bamboohr-broker` | `bamboohr-onboarding-request` | BambooHR | `signed_intent_only` |
| `workday-broker` | `workday-onboarding-request` | Workday | `signed_intent_only` |
| `gusto-broker` | `gusto-onboarding-request` | Gusto | `signed_intent_only` |

Each broker emits: `<vendor>_employee_create.{json|xml}`, `<vendor>_<assignment>.{json|xml}`, `signed_intent_envelope.md`, `tenant_admin_checklist.md`. Auth strings are always placeholders.

### Family C — IDP provisioning brokers (3 verticals, signed-intent-only with MFA enforcement)

| project_id | workflow_id | api_target.vendor | safety mode |
|---|---|---|---|
| `azure-ad-broker` | `azure-ad-provisioning-request` | Microsoft Graph | `signed_intent_only` |
| `okta-broker` | `okta-provisioning-request` | Okta | `signed_intent_only` |
| `google-workspace-broker` | `google-workspace-provisioning-request` | Google Workspace | `signed_intent_only` |

Each IDP broker additionally enforces `mfa_enforcement_required: true` and emits a `mfa_enforcement_report.json` alongside the user/group envelopes.

### Family D — Legal blueprint (1 vertical, blueprint-only)

| project_id | workflow_id | safety mode |
|---|---|---|
| `employment-contract-blueprint` | `employment-contract-blueprint-plan` | `blueprint_only` |

Output is a **jurisdiction-locked clause taxonomy** (13 clauses: probation, IP assignment, non-compete, non-solicitation, severance, notice period, working hours, leave, confidentiality, data protection, dispute resolution, termination for cause / without cause) plus an `attorney_review_checklist.md`. The skill **refuses** to produce finalized binding contract text; a licensed attorney in the target jurisdiction must review and finalize before any party signs.

## Safety contract matrix

| Family | `safety.mode` | Side effects | Network calls | Sign-off |
|---|---|---|---|---|
| A (SMB plan-only) | `plan_only` | None | None | Owner team |
| B (HRIS brokers) | `signed_intent_only` | None inside OctoAgent | Blocked | Tenant admin |
| C (IDP brokers) | `signed_intent_only` + MFA mandatory | None inside OctoAgent | Blocked | Tenant admin |
| D (Legal blueprint) | `blueprint_only` | None — no binding text | None | Licensed attorney |

A workflow MAY only mutate an external system if a human operator runs the emitted envelope through a credentialed CLI/curl path **out-of-band**. OctoAgent itself NEVER calls the external API.

## Wiring contract

Adding a new vertical now requires only the following 4 small edits, all in `backend/src/tools/builtins/ecosystem_workflow_tools.py`, plus one skill pack file:

1. Append an `IntegratedProject(...)` tuple to `INTEGRATED_PROJECTS`.
2. Add a command-id entry in `_command_for_project`.
3. Add the project_id to one of the registry dicts (`_VERTICAL_STEP_PACKS`, `_VERTICAL_ARTIFACT_PACKS`, `_VERTICAL_KINDS`, optional `_VERTICAL_EXTRA_RESULT_PACKS`).
4. Author `skills/public/<project_id>/SKILL.md` (frontmatter + Overview + Safety Model + Required Inputs + Output Contract + Workflow Steps + Refusal Cases).

The single tool entry `integrated_workflow_run_tool` (and its dispatch payload to the `task` subagent) is the universal execution surface — no new tool registration, no new gateway route, no new harness wiring is required for additional verticals.

## Test surface

`backend/tests/tools/test_ecosystem_workflow_tools.py` exercises:

- `test_phase8_all_verticals_status_ready` — every workflow returns `status="ready"` with a dispatch payload.
- `test_phase8_hris_brokers_emit_signed_intent_only` — HRIS family safety mode + placeholder secrets + envelope artifacts.
- `test_phase8_idp_brokers_enforce_mfa_and_block_network` — IDP family MFA enforcement + `mfa_enforcement_report.json`.
- `test_phase8_contract_blueprint_refuses_binding_text` — legal blueprint clause taxonomy + attorney review checklist.
- `test_phase8_smb_verticals_are_plan_only_with_owner_signoff` — SMB family `plan_only` safety + draft-only terminal step.
- `test_phase8_dispatch_prompts_carry_safety_terminal_step` — the safety step is **last** in every vertical's workflow so it is the last instruction the subagent reads.
- `test_phase8_catalog_lists_all_new_verticals_under_tier_a` — catalog visibility.
- `test_phase8_external_broker_filter_lists_brokers_only` — `integration_mode="external-broker"` filter returns brokers only, never SMB or legal verticals.

Plus the original three HR onboarding tests carried over from `5f3a17c`.

Full suite: 325 passed.

## What is still explicitly NOT done

- **Real production execution** of HRIS / IDP envelopes. OctoAgent does NOT include credentialed CLI helpers for any of these vendors; a tenant operator must own that path.
- **Legal-binding contract text generation.** The blueprint vertical refuses this by design.
- **Per-jurisdiction enriched compliance data** beyond the high-level matrix surfaced in artifacts. Real labor-law tables should be ingested via the storage/rag layer in a future phase.
- **Webhook receivers for HRIS/IDP confirmation callbacks.** Out of scope of plan-only/signed-intent-only verticals.
