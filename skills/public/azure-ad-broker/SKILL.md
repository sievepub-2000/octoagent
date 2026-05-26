---
name: azure-ad-broker
description: Plan-only Azure AD / Entra ID provisioning broker: emits Microsoft Graph user + group + license + MFA-enforcement request envelopes for tenant admin execution. OctoAgent never calls Graph directly.
---

# Azure AD / Entra ID Provisioning Broker

## Overview

This skill turns an account-provisioning brief into a **signed-intent envelope** for Azure AD / Entra ID. OctoAgent NEVER calls the identity provider directly; output is a structured request payload that an authorized tenant admin executes out-of-band.

## Safety Model

| Concern | Rule |
|---|---|
| Side effects | NONE inside OctoAgent. |
| Network calls | Blocked. |
| Secrets | Always placeholders. |
| MFA | Enforcement claim is mandatory in every envelope; refuse if MFA cannot be enforced for the target user. |
| Least privilege | The dispatched token MUST be scoped to user/group write only — admin/global scopes refused. |


## Required Inputs

1. `user_identity` (email, given_name, family_name)
2. `role_groups` (list of group names)
3. `tenant_id` (refuse if missing)
4. `license_sku` (optional)
5. `mfa_policy` (defaults to `enforced`)

## Output Contract

- `azure_ad_user_create.json` (json, required)
- `azure_ad_group_assignments.json` (json, required)
- `mfa_enforcement_report.json` (json, required)
- `signed_intent_envelope.md` (markdown, required)

## Workflow Steps

1. **intake** — collect user identity (email, given_name, family_name), required role-groups, MFA policy, license SKU; refuse if tenant_id is missing
2. **map_to_azure_ad_schema** — transform intake into azure_ad POST /users schema; validate required attributes (e.g. SCIM userName, displayName) and emit validation errors before envelope emission
3. **emit_user_create_envelope** — render the azure_ad POST /users HTTP request envelope (auth header placeholder, body, expected response shape) — no network call is made
4. **emit_group_assignment_envelope** — render the azure_ad POST /groups/{id}/members/$ref request envelope for each required role-group; one envelope per group
5. **mfa_enforcement_check** — emit explicit MFA-required claim in the envelope payload; if MFA cannot be enforced for the target user, refuse and report
6. **tenant_admin_signoff_gate** — surface tenant-admin checkboxes: scope of admin token, target tenant, dry-run mode, rollback (deletion) playbook reference; block dispatch until checked
7. **signed_intent_safety** — confirm OctoAgent never executes the request — output is a signed-intent envelope that a tenant admin runs out-of-band; tokens are placeholders

## Refusal Cases

- User asks OctoAgent to actually call the IDP API — refuse.
- `tenant_id` missing — refuse and ask.
- MFA cannot be enforced for the target user — refuse and report.
- Admin/global scopes requested — refuse; least-privilege only.
