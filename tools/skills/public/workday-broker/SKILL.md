---
name: workday-broker
description: Plan-only Workday onboarding broker: produces a signed-intent SOAP/REST envelope for the Hire business process. OctoAgent never calls Workday tenants directly; output is an artifact for a credentialed integration user.
---

# Workday Provisioning Broker

## Overview

This skill turns a hiring brief into a **signed-intent envelope** for the Workday API. OctoAgent NEVER calls the vendor API; output is a structured request payload (HTTP method, path, headers placeholders, body) that an authorized tenant admin executes out-of-band via a credentialed CLI or curl path.

## Safety Model

| Concern | Rule |
|---|---|
| Side effects | NONE inside OctoAgent. All outputs are draft envelopes. |
| Network calls | Blocked. The tool builds payloads only; no `requests`/`httpx` calls happen. |
| Secrets | Always placeholders (e.g. `<api_key>`); never inline real tokens. |
| Tenant admin sign-off | Required — the envelope is unsigned until the admin reviews scope, dry-run target, and rollback plan. |
| Rotation | Tenant admin rotates the API token after dispatch. |


## Required Inputs

1. `employee_identity` (name placeholders, email, region)
2. `role_title` and `start_date`
3. `manager_email`
4. `salary_band` (optional; placeholder when sensitive)
5. `tenant_subdomain_or_id`

## Output Contract

- `workday_hire_request.xml` (xml, required)
- `workday_security_role_assignment.xml` (xml, required)
- `signed_intent_envelope.md` (markdown, required)
- `tenant_admin_checklist.md` (markdown, required)

## Workflow Steps

1. **intake** — collect employee identity fields, role, start_date, region, manager, salary_band; refuse if PII inlined without explicit consent
2. **map_to_workday_schema** — transform intake into workday API schema fields; mark required vs optional and surface validation errors before envelope emission
3. **emit_employee_create_envelope** — render the workday employee-create HTTP request envelope (method, path, headers placeholders, JSON/XML body) as a draft artifact — no network call is made
4. **emit_onboarding_assignment_envelope** — render the workday onboarding/business_process assignment request envelope as a draft artifact
5. **tenant_admin_signoff_gate** — surface explicit checkboxes for tenant admin: credential rotation status, scope of API token, dry-run target, rollback procedure; block dispatch until checked
6. **signed_intent_safety** — confirm OctoAgent never executes the request — output is a signed-intent envelope an authorized operator runs out-of-band; payload contains placeholder secrets only

## Refusal Cases

- User asks OctoAgent to *send* the request directly — refuse; this is signed-intent only.
- Tenant id / subdomain missing — ask before producing the envelope.
- Real secrets pasted in the prompt — refuse and ask the user to use placeholders.
