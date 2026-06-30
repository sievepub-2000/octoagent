---
name: smb-hr-onboarding
description: Use this skill when a small or medium business (SMB) user needs to design, run, or audit a new-employee onboarding workflow. The skill produces a structured onboarding plan covering Day −7 → Day 30, including offer-letter checklist, equipment provisioning, accounts/access provisioning, compliance and policy delivery, first-week training agenda, mentor pairing, and Day-30 review. The skill is policy-aware (regional labor law, data-privacy, accessibility) and always produces a draft that requires explicit HR sign-off before any external side effects (sending offer letters, granting accounts, ordering hardware) are executed.
---

# SMB HR Onboarding Skill

## Overview

This skill turns a free-form hiring brief (role title, start date, location, employment type, reporting line, equipment preference) into a structured **OctoAgent SMB HR onboarding plan** that an HR generalist at a 5–500-employee company can review and execute. The plan is deterministic, locale-aware, and split across four named phases — `pre_arrival`, `day_one`, `first_week`, `day_thirty_review` — each with explicit owners, artifacts, and gates.

**Scope**: this is a *single-vertical* pilot (the first of OctoAgent's Phase 8 SMB verticals). It does NOT integrate with external HRIS / payroll providers (BambooHR, Workday, Gusto) and does NOT push changes to identity providers — every output is a draft for human execution.

## Authority & Safety Model

| Concern | Rule |
|---|---|
| Side effects | Plan-only. NEVER auto-send offer letters, create accounts, or order equipment. Outputs must be reviewable Markdown / JSON. |
| Compliance | The plan MUST surface region-specific labor-law gates as `compliance_gates` (e.g. mainland China labor contract within 1 month, EU GDPR data-handling consent, US I-9 within 3 business days). If region is unknown, ask before producing the plan. |
| PII | Treat name, contact, ID number, salary as restricted. Plan output uses placeholders (`{{employee_name}}`, `{{salary_band}}`) unless the user explicitly inlines values. |
| Accessibility | First-week training agenda MUST include an accommodations-check step before delivery. |
| Cultural lock | Output language follows `output_locale` (default `zh_CN`). |

## Required Inputs

The skill always asks for these before planning:

1. `role_title` — e.g. "Software Engineer II" / "客户成功经理"
2. `start_date` — ISO date or relative phrase ("next Monday")
3. `location` / `region` — country or city; drives compliance gates
4. `employment_type` — `full_time` / `part_time` / `contract` / `intern`
5. `reporting_line` — manager name or role; mentor optional
6. `equipment_profile` — `standard_office` / `dev_workstation` / `remote_only` / custom

Optional: `salary_band`, `internal_team_name`, `probation_period_days` (defaults to regional norm: 90 in US, 180 in CN, etc.).

## Output Contract

The skill returns ONE primary artifact `onboarding_plan.md` plus TWO companion JSON artifacts:

| Artifact | Format | Purpose |
|---|---|---|
| `onboarding_plan.md` | Markdown | Human-readable, four-phase agenda with owners, dates, and policy notes |
| `equipment_provisioning.json` | JSON | Machine-readable equipment + accounts request for IT ticketing |
| `compliance_checklist.json` | JSON | Region-keyed list of legal/policy gates with target completion date |

## Plan Skeleton

### Phase 1 — `pre_arrival` (Day −7 → Day 0)

- Confirm signed offer letter and (region-appropriate) employment contract on file
- Issue equipment per `equipment_profile`; verify delivery ≥48h before start
- Pre-create accounts (email, SSO, source control, ticketing, chat) — request only, do NOT auto-provision
- Send welcome packet with first-day logistics (address, time, attire, mentor name)
- Background check / right-to-work verification per region

### Phase 2 — `day_one`

- Greeter + workspace handoff (badge, desk, laptop)
- HR session: handbook delivery, policy acknowledgements, benefits enrolment window
- Manager 1:1: 30/60/90-day expectations, success metrics, first deliverable
- IT bootstrap: account login verification, MFA, VPN if remote
- Mentor lunch / virtual coffee

### Phase 3 — `first_week`

- Calendar template: 4× learning blocks, 2× team intros, 1× mentor sync, 1× manager retro
- Required compliance training (security, anti-harassment, region-specific) with completion deadlines
- First low-risk deliverable assigned with explicit acceptance criteria
- Accessibility / accommodations check-in with HR

### Phase 4 — `day_thirty_review`

- Manager → employee written feedback note
- Employee → company onboarding-quality survey (5-item Likert)
- Probation-period checkpoint flagged on calendar (configured per region)
- IT permissions review (least-privilege cleanup of any over-provisioned accounts)

## Quality Gates

Before final answer, validate:

- [ ] All four phases populated and dated against `start_date`
- [ ] `compliance_gates` non-empty when `region` is known
- [ ] `equipment_provisioning.json` enumerates each requested item with a target owner
- [ ] No PII inlined unless user explicitly provided it
- [ ] Output locale matches `output_locale`
- [ ] Disclaimer reminding the user this is a draft for HR review is included at the top of `onboarding_plan.md`

## Refusal Cases

Refuse politely and ask for clarification when:

- The request asks the agent to *send* offer letters, *create* accounts, or *push* changes to external systems — this skill is plan-only
- `region` is missing and user requests a compliance-grade plan
- The role title is for a regulated profession (healthcare practitioner, licensed financial advisor) without confirmation that licensing verification is owned by another process
