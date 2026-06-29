from __future__ import annotations

import json
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil
from langchain_core.tools import tool

from src.utils.datetime import utc_now_iso_seconds as _utc_now
from src.utils.serialization import fmt_json as _json


@dataclass(frozen=True)
class IntegratedProject:
    project_id: str
    display_name: str
    repo: str
    tier: str
    integration_modes: tuple[str, ...]
    summary: str
    skill_name: str | None = None
    plugin_id: str | None = None
    workflow_id: str | None = None
    risk: str = "review output before execution"


_PROJECTS_YAML = Path(__file__).with_name("ecosystem_projects.yaml")


def _load_projects() -> tuple[IntegratedProject, ...]:
    raw = yaml.safe_load(_PROJECTS_YAML.read_text(encoding="utf-8"))
    result: list[IntegratedProject] = []
    for item in raw:
        result.append(
            IntegratedProject(
                project_id=item["project_id"],
                display_name=item["display_name"],
                repo=item["repo"],
                tier=item["tier"],
                integration_modes=tuple(item["integration_modes"]),
                summary=item["summary"],
                skill_name=item.get("skill_name"),
                plugin_id=item.get("plugin_id"),
                workflow_id=item.get("workflow_id"),
                risk=item.get("risk", "review output before execution"),
            )
        )
    return tuple(result)


INTEGRATED_PROJECTS = _load_projects()

WORKFLOW_ALIASES = {project.workflow_id: project for project in INTEGRATED_PROJECTS if project.workflow_id}


def _project_payload(project: IntegratedProject) -> dict[str, Any]:
    return {
        "project_id": project.project_id,
        "display_name": project.display_name,
        "repo": project.repo,
        "tier": project.tier,
        "integration_modes": list(project.integration_modes),
        "summary": project.summary,
        "skill_name": project.skill_name,
        "plugin_id": project.plugin_id,
        "workflow_id": project.workflow_id,
        "risk": project.risk,
    }


def _runtime_process_sample(max_processes: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "ppid", "name", "cmdline", "status"]):
        try:
            info = proc.info
            cmdline = " ".join(str(part) for part in (info.get("cmdline") or []))
            haystack = f"{info.get('name') or ''} {cmdline}".lower()
            if not any(token in haystack for token in ("octoagent", "langgraph", "uvicorn", "next", "nginx")):
                continue
            rows.append({"pid": info.get("pid"), "ppid": info.get("ppid"), "name": info.get("name"), "status": info.get("status"), "cmdline": cmdline[:240], "reason": "matches OctoAgent runtime process filter"})
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return rows[:max_processes]


def _command_for_project(project: IntegratedProject) -> str:
    mapping = {
        "agent-rules-books": "arb:load-rules",
        "mirage-vfs": "mirage:vfs-plan",
        "peekaboo-vision-mcp": "peekaboo:capture-plan",
        "fireworks-tech-graph": "ftg:diagram",
        "beautiful-html-templates": "bht:deck",
        "goalbuddy": "goal:plan",
        "photo-agents": "photo:workflow",
        "lightseek-smg": "smg:gateway-plan",
        "tokenspeed": "tokenspeed:benchmark-plan",
        "witr": "witr:diagnose",
        "cheat-on-content": "coc:experiment",
        "cloakbrowser": "cloak:browser-plan",
        "lumibot": "lumibot:strategy-plan",
        "ian-handdrawn-ppt": "ian:blueprint",
        "smb-hr-onboarding": "hr:onboarding-plan",
        "bamboohr-broker": "bamboohr:onboarding-envelope",
        "workday-broker": "workday:onboarding-envelope",
        "gusto-broker": "gusto:onboarding-envelope",
        "azure-ad-broker": "azure-ad:provisioning-envelope",
        "okta-broker": "okta:provisioning-envelope",
        "google-workspace-broker": "gws:provisioning-envelope",
        "employment-contract-blueprint": "contract:blueprint",
        "smb-cs-playbook": "cs:playbook-plan",
        "smb-finance-close": "finance:close-plan",
        "smb-sales-motion": "sales:motion-plan",
        "smb-it-helpdesk-runbook": "helpdesk:runbook-plan",
    }
    return mapping.get(project.project_id, f"{project.project_id}:run")



# Phase 8 expansion: vertical step/artifact/safety registries (plan-only / signed-intent-only).
_VERTICAL_STEP_PACKS: dict[str, list[dict[str, Any]]] = {
    "bamboohr-broker": [
        {
            "step": "intake",
            "action": "collect employee identity fields, role, start_date, region, manager, salary_band; refuse if PII inlined without explicit consent"
        },
        {
            "step": "map_to_bamboohr_schema",
            "action": "transform intake into bamboohr API schema fields; mark required vs optional and surface validation errors before envelope emission"
        },
        {
            "step": "emit_employee_create_envelope",
            "action": "render the bamboohr employee-create HTTP request envelope (method, path, headers placeholders, JSON/XML body) as a draft artifact — no network call is made"
        },
        {
            "step": "emit_onboarding_assignment_envelope",
            "action": "render the bamboohr onboarding/checklist assignment request envelope as a draft artifact"
        },
        {
            "step": "tenant_admin_signoff_gate",
            "action": "surface explicit checkboxes for tenant admin: credential rotation status, scope of API token, dry-run target, rollback procedure; block dispatch until checked"
        },
        {
            "step": "signed_intent_safety",
            "action": "confirm OctoAgent never executes the request — output is a signed-intent envelope an authorized operator runs out-of-band; payload contains placeholder secrets only"
        }
    ],
    "workday-broker": [
        {
            "step": "intake",
            "action": "collect employee identity fields, role, start_date, region, manager, salary_band; refuse if PII inlined without explicit consent"
        },
        {
            "step": "map_to_workday_schema",
            "action": "transform intake into workday API schema fields; mark required vs optional and surface validation errors before envelope emission"
        },
        {
            "step": "emit_employee_create_envelope",
            "action": "render the workday employee-create HTTP request envelope (method, path, headers placeholders, JSON/XML body) as a draft artifact — no network call is made"
        },
        {
            "step": "emit_onboarding_assignment_envelope",
            "action": "render the workday onboarding/business_process assignment request envelope as a draft artifact"
        },
        {
            "step": "tenant_admin_signoff_gate",
            "action": "surface explicit checkboxes for tenant admin: credential rotation status, scope of API token, dry-run target, rollback procedure; block dispatch until checked"
        },
        {
            "step": "signed_intent_safety",
            "action": "confirm OctoAgent never executes the request — output is a signed-intent envelope an authorized operator runs out-of-band; payload contains placeholder secrets only"
        }
    ],
    "gusto-broker": [
        {
            "step": "intake",
            "action": "collect employee identity fields, role, start_date, region, manager, salary_band; refuse if PII inlined without explicit consent"
        },
        {
            "step": "map_to_gusto_schema",
            "action": "transform intake into gusto API schema fields; mark required vs optional and surface validation errors before envelope emission"
        },
        {
            "step": "emit_employee_create_envelope",
            "action": "render the gusto employee-create HTTP request envelope (method, path, headers placeholders, JSON/XML body) as a draft artifact — no network call is made"
        },
        {
            "step": "emit_onboarding_assignment_envelope",
            "action": "render the gusto onboarding/checklist assignment request envelope as a draft artifact"
        },
        {
            "step": "tenant_admin_signoff_gate",
            "action": "surface explicit checkboxes for tenant admin: credential rotation status, scope of API token, dry-run target, rollback procedure; block dispatch until checked"
        },
        {
            "step": "signed_intent_safety",
            "action": "confirm OctoAgent never executes the request — output is a signed-intent envelope an authorized operator runs out-of-band; payload contains placeholder secrets only"
        }
    ],
    "azure-ad-broker": [
        {
            "step": "intake",
            "action": "collect user identity (email, given_name, family_name), required role-groups, MFA policy, license SKU; refuse if tenant_id is missing"
        },
        {
            "step": "map_to_azure_ad_schema",
            "action": "transform intake into azure_ad POST /users schema; validate required attributes (e.g. SCIM userName, displayName) and emit validation errors before envelope emission"
        },
        {
            "step": "emit_user_create_envelope",
            "action": "render the azure_ad POST /users HTTP request envelope (auth header placeholder, body, expected response shape) — no network call is made"
        },
        {
            "step": "emit_group_assignment_envelope",
            "action": "render the azure_ad POST /groups/{id}/members/$ref request envelope for each required role-group; one envelope per group"
        },
        {
            "step": "mfa_enforcement_check",
            "action": "emit explicit MFA-required claim in the envelope payload; if MFA cannot be enforced for the target user, refuse and report"
        },
        {
            "step": "tenant_admin_signoff_gate",
            "action": "surface tenant-admin checkboxes: scope of admin token, target tenant, dry-run mode, rollback (deletion) playbook reference; block dispatch until checked"
        },
        {
            "step": "signed_intent_safety",
            "action": "confirm OctoAgent never executes the request — output is a signed-intent envelope that a tenant admin runs out-of-band; tokens are placeholders"
        }
    ],
    "okta-broker": [
        {
            "step": "intake",
            "action": "collect user identity (email, given_name, family_name), required role-groups, MFA policy, license SKU; refuse if tenant_id is missing"
        },
        {
            "step": "map_to_okta_schema",
            "action": "transform intake into okta POST /api/v1/users schema; validate required attributes (e.g. SCIM userName, displayName) and emit validation errors before envelope emission"
        },
        {
            "step": "emit_user_create_envelope",
            "action": "render the okta POST /api/v1/users HTTP request envelope (auth header placeholder, body, expected response shape) — no network call is made"
        },
        {
            "step": "emit_group_assignment_envelope",
            "action": "render the okta POST /api/v1/groups/{id}/users/{user_id} request envelope for each required role-group; one envelope per group"
        },
        {
            "step": "mfa_enforcement_check",
            "action": "emit explicit MFA-required claim in the envelope payload; if MFA cannot be enforced for the target user, refuse and report"
        },
        {
            "step": "tenant_admin_signoff_gate",
            "action": "surface tenant-admin checkboxes: scope of admin token, target tenant, dry-run mode, rollback (deletion) playbook reference; block dispatch until checked"
        },
        {
            "step": "signed_intent_safety",
            "action": "confirm OctoAgent never executes the request — output is a signed-intent envelope that a tenant admin runs out-of-band; tokens are placeholders"
        }
    ],
    "google-workspace-broker": [
        {
            "step": "intake",
            "action": "collect user identity (email, given_name, family_name), required role-groups, MFA policy, license SKU; refuse if tenant_id is missing"
        },
        {
            "step": "map_to_google_workspace_schema",
            "action": "transform intake into google_workspace POST /admin/directory/v1/users schema; validate required attributes (e.g. SCIM userName, displayName) and emit validation errors before envelope emission"
        },
        {
            "step": "emit_user_create_envelope",
            "action": "render the google_workspace POST /admin/directory/v1/users HTTP request envelope (auth header placeholder, body, expected response shape) — no network call is made"
        },
        {
            "step": "emit_group_assignment_envelope",
            "action": "render the google_workspace POST /admin/directory/v1/groups/{key}/members request envelope for each required role-group; one envelope per group"
        },
        {
            "step": "mfa_enforcement_check",
            "action": "emit explicit MFA-required claim in the envelope payload; if MFA cannot be enforced for the target user, refuse and report"
        },
        {
            "step": "tenant_admin_signoff_gate",
            "action": "surface tenant-admin checkboxes: scope of admin token, target tenant, dry-run mode, rollback (deletion) playbook reference; block dispatch until checked"
        },
        {
            "step": "signed_intent_safety",
            "action": "confirm OctoAgent never executes the request — output is a signed-intent envelope that a tenant admin runs out-of-band; tokens are placeholders"
        }
    ],
    "employment-contract-blueprint": [
        {
            "step": "intake",
            "action": "collect jurisdiction, role, employment_type (full_time/part_time/contract/intern), term (indefinite/fixed N months), industry, special concerns (remote, multi-jurisdiction). Refuse if jurisdiction is missing."
        },
        {
            "step": "jurisdiction_lock",
            "action": "lock the target jurisdiction; refuse to mix clauses across jurisdictions unless user explicitly opts in for a multi-jurisdiction summary"
        },
        {
            "step": "clause_taxonomy",
            "action": (
                "enumerate the standard clause headings expected in the chosen jurisdiction "
                "(probation, IP_assignment, non_compete, non_solicitation, severance, "
                "notice_period, working_hours, leave, confidentiality, data_protection, "
                "dispute_resolution, termination_for_cause, termination_without_cause); "
                "for each emit applicability + region-specific note "
                "(e.g. CA non-compete generally unenforceable; "
                "CN probation cap by contract term; EU GDPR data clauses)"
            )
        },
        {
            "step": "blueprint_render",
            "action": "render the clause blueprint as headings + bullet-point intents (NOT contract text); each clause carries a `requires_attorney_drafting: true` flag"
        },
        {
            "step": "attorney_review_gate",
            "action": "emit an explicit attorney-review checklist artifact listing each clause, jurisdiction note, and required external review item before any text is finalized"
        },
        {
            "step": "legal_safety",
            "action": "confirm output is a blueprint, not a contract; refuse if user asks to produce finalized binding contract text"
        }
    ],
    "smb-cs-playbook": [
        {
            "step": "intake",
            "action": "collect required customer success inputs and refuse to proceed when scope is undefined"
        },
        {
            "step": "kickoff_plan",
            "action": "produce the kickoff section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "d30_health_check_plan",
            "action": "produce the d30 health check section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "d60_health_check_plan",
            "action": "produce the d60 health check section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "d90_health_check_plan",
            "action": "produce the d90 health check section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "escalation_paths_plan",
            "action": "produce the escalation paths section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "qbr_template_plan",
            "action": "produce the qbr template section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "churn_save_runbook_plan",
            "action": "produce the churn save runbook section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "quality_gate",
            "action": "validate completeness, owner coverage, and acceptance criteria; refuse to finalize until gaps are addressed"
        },
        {
            "step": "draft_only_safety",
            "action": "confirm no external systems are mutated; all outputs are reviewable Markdown/JSON drafts for the responsible team"
        }
    ],
    "smb-finance-close": [
        {
            "step": "intake",
            "action": "collect required month-end close inputs and refuse to proceed when scope is undefined"
        },
        {
            "step": "bank_recon_plan",
            "action": "produce the bank recon section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "accruals_plan",
            "action": "produce the accruals section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "revenue_recognition_cutoff_plan",
            "action": "produce the revenue recognition cutoff section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "expense_classification_plan",
            "action": "produce the expense classification section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "tax_provision_check_plan",
            "action": "produce the tax provision check section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "close_packet_plan",
            "action": "produce the close packet section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "audit_trail_review_plan",
            "action": "produce the audit trail review section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "quality_gate",
            "action": "validate completeness, owner coverage, and acceptance criteria; refuse to finalize until gaps are addressed"
        },
        {
            "step": "draft_only_safety",
            "action": "confirm no external systems are mutated; all outputs are reviewable Markdown/JSON drafts for the responsible team"
        }
    ],
    "smb-sales-motion": [
        {
            "step": "intake",
            "action": "collect required sales motion inputs and refuse to proceed when scope is undefined"
        },
        {
            "step": "icp_definition_plan",
            "action": "produce the icp definition section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "outbound_cadence_plan",
            "action": "produce the outbound cadence section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "discovery_script_plan",
            "action": "produce the discovery script section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "demo_template_plan",
            "action": "produce the demo template section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "proposal_template_plan",
            "action": "produce the proposal template section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "negotiation_guardrails_plan",
            "action": "produce the negotiation guardrails section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "handoff_to_cs_plan",
            "action": "produce the handoff to cs section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "quality_gate",
            "action": "validate completeness, owner coverage, and acceptance criteria; refuse to finalize until gaps are addressed"
        },
        {
            "step": "draft_only_safety",
            "action": "confirm no external systems are mutated; all outputs are reviewable Markdown/JSON drafts for the responsible team"
        }
    ],
    "smb-it-helpdesk-runbook": [
        {
            "step": "intake",
            "action": "collect required IT helpdesk inputs and refuse to proceed when scope is undefined"
        },
        {
            "step": "ticket_triage_plan",
            "action": "produce the ticket triage section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "priority_matrix_plan",
            "action": "produce the priority matrix section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "password_reset_sop_plan",
            "action": "produce the password reset sop section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "equipment_request_sop_plan",
            "action": "produce the equipment request sop section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "access_request_sop_plan",
            "action": "produce the access request sop section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "escalation_paths_plan",
            "action": "produce the escalation paths section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "sla_definitions_plan",
            "action": "produce the sla definitions section with explicit owners, due dates, and acceptance criteria"
        },
        {
            "step": "quality_gate",
            "action": "validate completeness, owner coverage, and acceptance criteria; refuse to finalize until gaps are addressed"
        },
        {
            "step": "draft_only_safety",
            "action": "confirm no external systems are mutated; all outputs are reviewable Markdown/JSON drafts for the responsible team"
        }
    ]
}

_VERTICAL_ARTIFACT_PACKS: dict[str, list[dict[str, Any]]] = {
    "bamboohr-broker": [
        {
            "name": "bamboohr_employee_create.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "bamboohr_onboarding_assignment.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "signed_intent_envelope.md",
            "kind": "markdown",
            "required": True
        },
        {
            "name": "tenant_admin_checklist.md",
            "kind": "markdown",
            "required": True
        }
    ],
    "workday-broker": [
        {
            "name": "workday_hire_request.xml",
            "kind": "xml",
            "required": True
        },
        {
            "name": "workday_security_role_assignment.xml",
            "kind": "xml",
            "required": True
        },
        {
            "name": "signed_intent_envelope.md",
            "kind": "markdown",
            "required": True
        },
        {
            "name": "tenant_admin_checklist.md",
            "kind": "markdown",
            "required": True
        }
    ],
    "gusto-broker": [
        {
            "name": "gusto_employee_create.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "gusto_payroll_setup.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "signed_intent_envelope.md",
            "kind": "markdown",
            "required": True
        },
        {
            "name": "tenant_admin_checklist.md",
            "kind": "markdown",
            "required": True
        }
    ],
    "azure-ad-broker": [
        {
            "name": "azure_ad_user_create.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "azure_ad_group_assignments.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "mfa_enforcement_report.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "signed_intent_envelope.md",
            "kind": "markdown",
            "required": True
        }
    ],
    "okta-broker": [
        {
            "name": "okta_user_create.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "okta_group_assignments.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "mfa_enforcement_report.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "signed_intent_envelope.md",
            "kind": "markdown",
            "required": True
        }
    ],
    "google-workspace-broker": [
        {
            "name": "google_workspace_user_create.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "google_workspace_group_assignments.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "mfa_enforcement_report.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "signed_intent_envelope.md",
            "kind": "markdown",
            "required": True
        }
    ],
    "employment-contract-blueprint": [
        {
            "name": "contract_clause_blueprint.md",
            "kind": "markdown",
            "required": True
        },
        {
            "name": "jurisdiction_compliance_matrix.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "attorney_review_checklist.md",
            "kind": "markdown",
            "required": True
        }
    ],
    "smb-cs-playbook": [
        {
            "name": "cs_playbook.md",
            "kind": "markdown",
            "required": True
        },
        {
            "name": "health_score_matrix.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "escalation_runbook.md",
            "kind": "markdown",
            "required": True
        }
    ],
    "smb-finance-close": [
        {
            "name": "close_checklist.md",
            "kind": "markdown",
            "required": True
        },
        {
            "name": "reconciliation_matrix.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "audit_trail.json",
            "kind": "json",
            "required": True
        }
    ],
    "smb-sales-motion": [
        {
            "name": "sales_motion_playbook.md",
            "kind": "markdown",
            "required": True
        },
        {
            "name": "deal_stage_definitions.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "handoff_packet.md",
            "kind": "markdown",
            "required": True
        }
    ],
    "smb-it-helpdesk-runbook": [
        {
            "name": "helpdesk_runbook.md",
            "kind": "markdown",
            "required": True
        },
        {
            "name": "sla_matrix.json",
            "kind": "json",
            "required": True
        },
        {
            "name": "triage_decision_tree.md",
            "kind": "markdown",
            "required": True
        }
    ]
}

_VERTICAL_EXTRA_RESULT_PACKS: dict[str, dict[str, Any]] = {
    "bamboohr-broker": {
        "api_target": {
            "vendor": "BambooHR",
            "base_url_template": "https://api.bamboohr.com/api/gateway.php/{subdomain}/v1",
            "endpoints": [
                "POST /employees",
                "POST /employees/{id}/onboarding/items"
            ],
            "auth": "Basic <api_key>:x (placeholder; rotate before dispatch)"
        }
    },
    "workday-broker": {
        "api_target": {
            "vendor": "Workday",
            "base_url_template": "https://wd2-impl-services1.workday.com/ccx/service/{tenant}",
            "endpoints": [
                "Hire (Staffing v40.x SOAP)",
                "Assign_Roles (HR v40.x SOAP)"
            ],
            "auth": "WS-Security UsernameToken (placeholder; rotate before dispatch)"
        }
    },
    "gusto-broker": {
        "api_target": {
            "vendor": "Gusto",
            "base_url_template": "https://api.gusto.com/v1",
            "endpoints": [
                "POST /companies/{company_id}/employees",
                "POST /employees/{employee_id}/onboarding_status"
            ],
            "auth": "Bearer <oauth2_token> (placeholder; rotate before dispatch)"
        }
    },
    "azure-ad-broker": {
        "api_target": {
            "vendor": "Microsoft Graph",
            "base_url_template": "https://graph.microsoft.com/v1.0",
            "endpoints": [
                "POST /users",
                "POST /groups/{group_id}/members/$ref",
                "PATCH /users/{user_id}/authentication/methods"
            ],
            "auth": "Bearer <ms_graph_token> (placeholder; least-privilege Directory.ReadWrite.All only)"
        }
    },
    "okta-broker": {
        "api_target": {
            "vendor": "Okta",
            "base_url_template": "https://{tenant}.okta.com",
            "endpoints": [
                "POST /api/v1/users?activate=true",
                "PUT /api/v1/groups/{group_id}/users/{user_id}",
                "POST /api/v1/users/{user_id}/factors"
            ],
            "auth": "SSWS <okta_api_token> (placeholder; rotate before dispatch)"
        }
    },
    "google-workspace-broker": {
        "api_target": {
            "vendor": "Google Workspace",
            "base_url_template": "https://admin.googleapis.com",
            "endpoints": [
                "POST /admin/directory/v1/users",
                "POST /admin/directory/v1/groups/{group_key}/members",
                "POST /admin/directory/v1/users/{user_key}/twoStepVerification"
            ],
            "auth": "Bearer <oauth2_admin_token> (placeholder; least-privilege admin.directory.user scope only)"
        }
    },
    "employment-contract-blueprint": {
        "clause_taxonomy": [
            "probation",
            "ip_assignment",
            "non_compete",
            "non_solicitation",
            "severance",
            "notice_period",
            "working_hours",
            "leave",
            "confidentiality",
            "data_protection",
            "dispute_resolution",
            "termination_for_cause",
            "termination_without_cause"
        ]
    },
    "smb-cs-playbook": {
        "cs_phases": [
            {
                "phase": "kickoff",
                "day_range": "D0..D7",
                "owner": "CSM"
            },
            {
                "phase": "d30_health_check",
                "day_range": "D30",
                "owner": "CSM"
            },
            {
                "phase": "d60_health_check",
                "day_range": "D60",
                "owner": "CSM + Lead"
            },
            {
                "phase": "d90_health_check",
                "day_range": "D90",
                "owner": "CSM + Lead"
            },
            {
                "phase": "qbr",
                "day_range": "Quarterly",
                "owner": "CSM + AE"
            }
        ]
    },
    "smb-finance-close": {
        "close_steps_summary": [
            "bank_recon → accruals → revenue_recognition_cutoff → expense_classification → tax_provision_check → close_packet → audit_trail_review"
        ]
    },
    "smb-sales-motion": {
        "stage_summary": [
            "icp",
            "outbound",
            "discovery",
            "demo",
            "proposal",
            "negotiation",
            "closed_won",
            "handoff_to_cs"
        ]
    },
    "smb-it-helpdesk-runbook": {
        "priority_matrix": [
            {
                "priority": "P1",
                "definition": "production outage / blocking access for >1 user",
                "first_response": "15m"
            },
            {
                "priority": "P2",
                "definition": "blocking access for 1 user",
                "first_response": "1h"
            },
            {
                "priority": "P3",
                "definition": "non-blocking",
                "first_response": "1bd"
            },
            {
                "priority": "P4",
                "definition": "request / informational",
                "first_response": "3bd"
            }
        ]
    }
}

_VERTICAL_KINDS: dict[str, str] = {
    "bamboohr-broker": "hris",
    "workday-broker": "hris",
    "gusto-broker": "hris",
    "azure-ad-broker": "idp",
    "okta-broker": "idp",
    "google-workspace-broker": "idp",
    "employment-contract-blueprint": "legal",
    "smb-cs-playbook": "smb",
    "smb-finance-close": "smb",
    "smb-sales-motion": "smb",
    "smb-it-helpdesk-runbook": "smb"
}

_SAFETY_PACKS: dict[str, dict[str, Any]] = {
    "hris": {
        "mode": "signed_intent_only",
        "auto_side_effects_enabled": False,
        "network_calls_blocked": True,
        "requires_tenant_admin_signoff": True,
        "secrets_in_payload": "placeholders_only",
        "operator_path": "credentialed_cli_or_curl_out_of_band"
    },
    "idp": {
        "mode": "signed_intent_only",
        "auto_side_effects_enabled": False,
        "network_calls_blocked": True,
        "requires_tenant_admin_signoff": True,
        "secrets_in_payload": "placeholders_only",
        "mfa_enforcement_required": True,
        "operator_path": "credentialed_cli_or_curl_out_of_band"
    },
    "legal": {
        "mode": "blueprint_only",
        "binding_text_generated": False,
        "attorney_review_required": True,
        "jurisdiction_locked": True,
        "must_not_finalize_without_counsel": True,
        "disclaimer": "OctoAgent outputs are NOT legal advice; a licensed attorney in the target jurisdiction must review and finalize before any party signs"
    },
    "smb": {
        "mode": "plan_only",
        "auto_side_effects_enabled": False,
        "requires_owner_signoff": True,
        "external_systems_mutated": False
    }
}

def _workflow_steps(project: IntegratedProject) -> list[dict[str, Any]]:
    base = [
        {"step": "load_capability", "tool": "list_capabilities", "args": {"kind": "plugin", "enabled_only": True}},
        {"step": "resolve_plugin", "tool": "get_plugin_command", "args": {"command_id": _command_for_project(project)}},
    ]
    if project.skill_name:
        base.append({"step": "load_skill", "tool": "load_skill", "args": {"skill_name": project.skill_name}})
    if project.project_id == "ian-handdrawn-ppt":
        base.extend(
            [
                {"step": "intake", "action": "extract audience, lesson objective, and visual constraints"},
                {"step": "blueprint", "action": "produce 1 cover and 3 page image briefs with required text only"},
                {"step": "quality_gate", "action": "check Chinese text length, style lock, aspect ratio, and contact sheet readiness"},
            ]
        )
    elif project.project_id == "lumibot":
        base.extend(
            [
                {"step": "research_scope", "action": "classify asset universe, data source, time horizon, and paper-trading limits"},
                {"step": "strategy_outline", "action": "define signal, risk model, backtest window, and evaluation metrics"},
                {"step": "safety_gate", "action": "block live trading and require explicit paper-trading configuration"},
            ]
        )
    elif project.project_id == "smb-hr-onboarding":
        base.extend(
            [
                {"step": "intake", "action": "collect role_title, start_date, region, employment_type, reporting_line, equipment_profile; ask before planning if region is missing"},
                {"step": "pre_arrival_plan", "action": "build Day -7 -> Day 0 checklist: signed contract, equipment dispatch >=48h before start, accounts request (no auto-provision), welcome packet, right-to-work verification"},
                {"step": "day_one_plan", "action": "produce Day-1 agenda: greeter + workspace, HR policy acknowledgements, manager 1:1 with 30/60/90 expectations, IT bootstrap (login + MFA + VPN), mentor lunch"},
                {"step": "first_week_plan", "action": "produce first-week calendar with learning blocks, team intros, mentor sync, manager retro, required compliance trainings, first low-risk deliverable, accessibility check-in"},
                {"step": "day_thirty_review_plan", "action": "schedule manager written feedback note, employee survey, probation checkpoint, least-privilege IT permission review"},
                {"step": "compliance_gate", "action": "emit region-keyed compliance_gates list (e.g. CN labor contract <=30 days, US I-9 <=3 business days, EU GDPR consent) and refuse if region unknown"},
                {"step": "draft_only_safety", "action": "confirm no offer-letter sending, no account creation, no equipment ordering happens automatically; all outputs are reviewable Markdown/JSON drafts"},
            ]
        )
    elif project.project_id == "witr":
        base.append({"step": "runtime_probe", "action": "collect OctoAgent process sample with psutil"})
    elif project.project_id in _VERTICAL_STEP_PACKS:
        base.extend(_VERTICAL_STEP_PACKS[project.project_id])
    else:
        base.extend(
            [
                {"step": "plan", "action": "turn the user request into a bounded workflow contract"},
                {"step": "execute", "action": "use the matched skill/plugin/tool guidance and produce artifacts"},
                {"step": "review", "action": "validate outputs against policy, user goal, and artifact quality gates"},
            ]
        )
    return base


def _format_dispatch_prompt(
    project: IntegratedProject,
    user_prompt: str,
    steps: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    quality_gates: list[str],
) -> str:
    """Render a self-contained execution brief for a subagent.

    The brief is deterministic, plain text, and contains all context the
    subagent needs so the lead agent does not have to inline the plan into
    its own ``task`` prompt by hand.
    """

    step_lines: list[str] = []
    for index, step in enumerate(steps, start=1):
        name = step.get("step", f"step_{index}")
        if "tool" in step:
            args = step.get("args") or {}
            args_repr = json.dumps(args, ensure_ascii=False, sort_keys=True)
            step_lines.append(f"{index}. {name} — call tool `{step['tool']}` with args {args_repr}")
        else:
            action = step.get("action", "")
            step_lines.append(f"{index}. {name} — {action}")
    artifact_lines = [
        f"- {item['name']} ({item['kind']}{', required' if item.get('required') else ''})"
        for item in artifacts
    ]
    gate_lines = [f"- {gate}" for gate in quality_gates]
    return (
        f"You are executing the OctoAgent integrated workflow "
        f"`{project.workflow_id}` ({project.display_name}).\n\n"
        f"User request:\n{user_prompt.strip()}\n\n"
        f"Execute the following plan in order, using your available tools. "
        f"Stop and report instead of guessing if a tool is missing or fails.\n\n"
        f"Plan:\n" + "\n".join(step_lines) + "\n\n"
        "Expected artifacts:\n" + "\n".join(artifact_lines) + "\n\n"
        "Quality gates (must pass before final answer):\n" + "\n".join(gate_lines) + "\n\n"
        "Return a concise structured summary of what you did, the artifacts you produced, "
        "and any quality-gate failures."
    )


def _build_dispatch_payload(
    project: IntegratedProject,
    user_prompt: str,
    steps: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    quality_gates: list[str],
) -> dict[str, Any]:
    """Build ready-to-use ``task()`` kwargs for executing the workflow.

    The lead agent can chain ``task(**dispatch)`` to hand off the entire plan
    to a general-purpose subagent without any further reformatting.
    """

    description = f"run workflow {project.workflow_id}"[:60]
    return {
        "description": description,
        "prompt": _format_dispatch_prompt(project, user_prompt, steps, artifacts, quality_gates),
        "subagent_type": "general-purpose",
    }


@tool("integrated_project_catalog", parse_docstring=True)
def integrated_project_catalog_tool(tier: str = "all", integration_mode: str = "all", max_items: int = 50) -> str:
    """List OctoAgent-integrated upstream project capabilities.

    Args:
        tier: Filter by S, A, B, or all.
        integration_mode: Filter by mode such as skills, plugin, system-tool, mcp-template, or all.
        max_items: Maximum number of projects returned.
    """

    normalized_tier = tier.strip().upper()
    normalized_mode = integration_mode.strip().lower()
    projects = list(INTEGRATED_PROJECTS)
    if normalized_tier not in {"", "ALL", "ANY"}:
        projects = [project for project in projects if project.tier == normalized_tier]
    if normalized_mode not in {"", "all", "any"}:
        projects = [project for project in projects if normalized_mode in project.integration_modes]
    limited = projects[: max(1, min(int(max_items), 100))]
    return _json({"generated_at": _utc_now(), "returned": len(limited), "truncated": len(projects) > len(limited), "projects": [_project_payload(project) for project in limited]})


@tool("integrated_workflow_run", parse_docstring=True)
def integrated_workflow_run_tool(workflow_id: str, prompt: str, dry_run: bool = True) -> str:
    """Plan an OctoAgent integrated workflow and return a ready-to-execute dispatch payload.

    This tool is the deterministic planner for installed upstream-derived
    skills/plugins. It always returns a verified ``tool_call_sequence`` plus a
    ``dispatch`` payload that the lead agent can hand directly to ``task`` for
    end-to-end execution by a subagent — no manual reformatting required.

    Recommended chain pattern::

        plan = integrated_workflow_run(workflow_id="...", prompt="...")
        # review plan["tool_call_sequence"] and plan["expected_artifacts"]
        # then, to actually execute:
        task(**plan["dispatch"])

    The ``dispatch`` payload contains ``description``, ``prompt`` and
    ``subagent_type`` keys suitable for direct ``task(**dispatch)`` invocation.
    The planner itself produces no side effects regardless of ``dry_run``;
    side effects only occur after the lead agent issues the ``task`` call.

    Args:
        workflow_id: Workflow ID from integrated_project_catalog.
        prompt: User task or source material to run through the workflow.
        dry_run: Reserved for future side-effecting planner variants; today the
            planner is always side-effect-free and ``dispatch`` is the
            execution handoff.
    """

    normalized = workflow_id.strip()
    project = WORKFLOW_ALIASES.get(normalized)
    if project is None:
        return _json({"generated_at": _utc_now(), "error": f"unknown workflow_id: {workflow_id}", "available_workflows": sorted(WORKFLOW_ALIASES)})
    artifacts: list[dict[str, Any]] = [
        {"name": "workflow_summary", "kind": "json", "required": True},
        {"name": "review_notes", "kind": "markdown", "required": True},
    ]
    if project.project_id in {"fireworks-tech-graph", "beautiful-html-templates", "ian-handdrawn-ppt"}:
        artifacts.append({"name": "visual_blueprint", "kind": "markdown", "required": True})
    if project.project_id == "witr":
        artifacts.append({"name": "runtime_process_sample", "kind": "json", "required": True})
    if project.project_id == "smb-hr-onboarding":
        artifacts.extend(
            [
                {"name": "onboarding_plan.md", "kind": "markdown", "required": True},
                {"name": "equipment_provisioning.json", "kind": "json", "required": True},
                {"name": "compliance_checklist.json", "kind": "json", "required": True},
            ]
        )
    if project.project_id in _VERTICAL_ARTIFACT_PACKS:
        artifacts.extend(_VERTICAL_ARTIFACT_PACKS[project.project_id])
    steps = _workflow_steps(project)
    quality_gates = [
        "capability is installed and enabled",
        "skill or plugin command is loaded before execution",
        "outputs match the requested artifact format",
        "policy and user-authorization constraints are checked before side effects",
    ]
    result: dict[str, Any] = {
        "generated_at": _utc_now(),
        "workflow_id": normalized,
        "dry_run": dry_run,
        "project": _project_payload(project),
        "input_excerpt": prompt.strip()[:500],
        "tool_call_sequence": steps,
        "expected_artifacts": artifacts,
        "quality_gates": quality_gates,
        "dispatch": _build_dispatch_payload(project, prompt, steps, artifacts, quality_gates),
        "status": "ready",
    }
    if project.project_id == "witr":
        result["runtime_process_sample"] = _runtime_process_sample()
    if project.project_id == "ian-handdrawn-ppt":
        result["slide_blueprint"] = [
            {"page": "cover", "aspect_ratio": "21:9", "purpose": "one clear metaphor for the source material"},
            {"page": "page-01", "aspect_ratio": "16:9", "purpose": "first core idea, minimal Chinese text"},
            {"page": "page-02", "aspect_ratio": "16:9", "purpose": "process or contrast view"},
            {"page": "page-03", "aspect_ratio": "16:9", "purpose": "summary or decision frame"},
        ]
    if project.project_id == "lumibot":
        result["trading_safety"] = {"mode": "research_or_paper_trading_only", "live_trading_enabled": False, "requires_explicit_broker_config": True}
    if project.project_id == "smb-hr-onboarding":
        result["onboarding_phases"] = [
            {"phase": "pre_arrival", "day_range": "D-7..D0", "owner": "HR + IT"},
            {"phase": "day_one", "day_range": "D1", "owner": "Manager + HR"},
            {"phase": "first_week", "day_range": "D2..D7", "owner": "Manager + Mentor"},
            {"phase": "day_thirty_review", "day_range": "D30", "owner": "Manager + HR"},
        ]
        result["compliance_safety"] = {
            "mode": "plan_only",
            "auto_side_effects_enabled": False,
            "requires_hr_signoff": True,
            "region_gates_required": True,
            "pii_inlining": "placeholders_unless_explicit",
        }
    if project.project_id in _VERTICAL_KINDS:
        result["safety"] = _SAFETY_PACKS[_VERTICAL_KINDS[project.project_id]]
        extras = _VERTICAL_EXTRA_RESULT_PACKS.get(project.project_id)
        if extras:
            result.update(extras)
    return _json(result)


ECOSYSTEM_WORKFLOW_TOOLS = [integrated_project_catalog_tool, integrated_workflow_run_tool]
