from __future__ import annotations

import json

from src.tools.builtins.ecosystem_workflow_tools import integrated_project_catalog_tool, integrated_workflow_run_tool


def test_integrated_project_catalog_lists_s_and_a_projects() -> None:
    payload = json.loads(integrated_project_catalog_tool.invoke({"tier": "A", "max_items": 20}))
    project_ids = {item["project_id"] for item in payload["projects"]}

    assert "goalbuddy" in project_ids
    assert "tokenspeed" in project_ids
    assert "witr" in project_ids


def test_integrated_workflow_run_returns_tool_sequence() -> None:
    payload = json.loads(integrated_workflow_run_tool.invoke({"workflow_id": "ian-handdrawn-ppt", "prompt": "Explain OctoAgent workflow."}))

    assert payload["status"] == "ready"
    assert payload["project"]["plugin_id"] == "ian-handdrawn-ppt"
    assert any(step.get("tool") == "load_skill" for step in payload["tool_call_sequence"])
    assert payload["slide_blueprint"][0]["aspect_ratio"] == "21:9"


def test_lumibot_workflow_is_paper_trading_only() -> None:
    payload = json.loads(integrated_workflow_run_tool.invoke({"workflow_id": "lumibot-research-strategy", "prompt": "Research a mean reversion strategy."}))

    assert payload["trading_safety"]["live_trading_enabled"] is False
    assert payload["project"]["tier"] == "B"



def test_integrated_workflow_run_includes_dispatch_payload() -> None:
    payload = json.loads(
        integrated_workflow_run_tool.invoke(
            {"workflow_id": "ian-handdrawn-ppt", "prompt": "Visualize the OctoAgent runtime."}
        )
    )

    dispatch = payload["dispatch"]
    assert set(dispatch.keys()) == {"description", "prompt", "subagent_type"}
    assert dispatch["subagent_type"] == "general-purpose"
    assert "ian-handdrawn-ppt" in dispatch["description"]
    assert "Visualize the OctoAgent runtime." in dispatch["prompt"]
    assert "load_skill" in dispatch["prompt"]
    assert "Quality gates" in dispatch["prompt"]


def test_integrated_workflow_run_dispatch_unknown_workflow_omits_dispatch() -> None:
    payload = json.loads(
        integrated_workflow_run_tool.invoke({"workflow_id": "no-such-workflow", "prompt": "x"})
    )
    assert "error" in payload
    assert "dispatch" not in payload


def test_integrated_workflow_run_dispatch_is_self_contained() -> None:
    payload = json.loads(
        integrated_workflow_run_tool.invoke({"workflow_id": "witr-runtime-diagnosis", "prompt": "Probe runtime."})
    )

    dispatch_prompt = payload["dispatch"]["prompt"]
    for step in payload["tool_call_sequence"]:
        marker = step.get("tool") or step.get("step")
        assert marker in dispatch_prompt, f"dispatch prompt missing step marker: {marker}"
    for artifact in payload["expected_artifacts"]:
        assert artifact["name"] in dispatch_prompt



def test_smb_hr_onboarding_workflow_returns_phases_and_safety() -> None:
    payload = json.loads(
        integrated_workflow_run_tool.invoke(
            {"workflow_id": "smb-hr-onboarding-plan", "prompt": "Plan onboarding for a remote engineer joining next Monday in Shenzhen."}
        )
    )

    assert payload["status"] == "ready"
    assert payload["project"]["project_id"] == "smb-hr-onboarding"
    phases = {entry["phase"] for entry in payload["onboarding_phases"]}
    assert phases == {"pre_arrival", "day_one", "first_week", "day_thirty_review"}
    safety = payload["compliance_safety"]
    assert safety["mode"] == "plan_only"
    assert safety["auto_side_effects_enabled"] is False
    assert safety["requires_hr_signoff"] is True
    artifact_names = {a["name"] for a in payload["expected_artifacts"]}
    assert {"onboarding_plan.md", "equipment_provisioning.json", "compliance_checklist.json"}.issubset(artifact_names)


def test_smb_hr_onboarding_dispatch_carries_compliance_steps() -> None:
    payload = json.loads(
        integrated_workflow_run_tool.invoke(
            {"workflow_id": "smb-hr-onboarding-plan", "prompt": "Onboarding for a customer success manager in Berlin."}
        )
    )

    dispatch_prompt = payload["dispatch"]["prompt"]
    assert "compliance_gate" in dispatch_prompt
    assert "draft_only_safety" in dispatch_prompt
    assert "day_one_plan" in dispatch_prompt
    assert "load_skill" in dispatch_prompt
    assert payload["dispatch"]["subagent_type"] == "general-purpose"


def test_smb_hr_onboarding_is_listed_in_catalog() -> None:
    payload = json.loads(
        integrated_project_catalog_tool.invoke({"tier": "A", "integration_mode": "workflow", "max_items": 50})
    )
    ids = {item["project_id"] for item in payload["projects"]}
    assert "smb-hr-onboarding" in ids



# ---------------------------------------------------------------
# Phase 8 expansion: HRIS / IDP / legal-blueprint / SMB verticals.
# ---------------------------------------------------------------

HRIS_WORKFLOWS = [
    "bamboohr-onboarding-request",
    "workday-onboarding-request",
    "gusto-onboarding-request",
]
IDP_WORKFLOWS = [
    "azure-ad-provisioning-request",
    "okta-provisioning-request",
    "google-workspace-provisioning-request",
]
LEGAL_WORKFLOWS = ["employment-contract-blueprint-plan"]
SMB_VERTICAL_WORKFLOWS = [
    "smb-cs-playbook-plan",
    "smb-finance-close-plan",
    "smb-sales-motion-plan",
    "smb-it-helpdesk-runbook-plan",
]


def _run(wf: str, prompt: str = "Plan a representative request.") -> dict:
    return json.loads(integrated_workflow_run_tool.invoke({"workflow_id": wf, "prompt": prompt}))


def test_phase8_all_verticals_status_ready() -> None:
    for wf in HRIS_WORKFLOWS + IDP_WORKFLOWS + LEGAL_WORKFLOWS + SMB_VERTICAL_WORKFLOWS:
        payload = _run(wf)
        assert payload["status"] == "ready", f"{wf} not ready"
        assert "dispatch" in payload
        assert payload["dispatch"]["subagent_type"] == "general-purpose"


def test_phase8_hris_brokers_emit_signed_intent_only() -> None:
    for wf in HRIS_WORKFLOWS:
        payload = _run(wf)
        safety = payload["safety"]
        assert safety["mode"] == "signed_intent_only"
        assert safety["auto_side_effects_enabled"] is False
        assert safety["network_calls_blocked"] is True
        assert safety["requires_tenant_admin_signoff"] is True
        assert safety["secrets_in_payload"] == "placeholders_only"
        names = {a["name"] for a in payload["expected_artifacts"]}
        assert "signed_intent_envelope.md" in names
        assert "tenant_admin_checklist.md" in names
        assert payload["api_target"]["auth"].startswith(("Basic", "WS-Security", "Bearer"))
        assert "placeholder" in payload["api_target"]["auth"]


def test_phase8_idp_brokers_enforce_mfa_and_block_network() -> None:
    for wf in IDP_WORKFLOWS:
        payload = _run(wf)
        safety = payload["safety"]
        assert safety["mode"] == "signed_intent_only"
        assert safety["network_calls_blocked"] is True
        assert safety["mfa_enforcement_required"] is True
        steps = {s.get("step") for s in payload["tool_call_sequence"]}
        assert "mfa_enforcement_check" in steps
        assert "tenant_admin_signoff_gate" in steps
        names = {a["name"] for a in payload["expected_artifacts"]}
        assert "mfa_enforcement_report.json" in names
        assert "signed_intent_envelope.md" in names


def test_phase8_contract_blueprint_refuses_binding_text() -> None:
    payload = _run("employment-contract-blueprint-plan", "Draft an employment contract for a senior engineer in California.")
    safety = payload["safety"]
    assert safety["mode"] == "blueprint_only"
    assert safety["binding_text_generated"] is False
    assert safety["attorney_review_required"] is True
    assert safety["jurisdiction_locked"] is True
    assert safety["must_not_finalize_without_counsel"] is True
    taxonomy = payload["clause_taxonomy"]
    assert "non_compete" in taxonomy
    assert "ip_assignment" in taxonomy
    assert "dispute_resolution" in taxonomy
    steps = {s.get("step") for s in payload["tool_call_sequence"]}
    assert "jurisdiction_lock" in steps
    assert "attorney_review_gate" in steps
    assert "legal_safety" in steps
    names = {a["name"] for a in payload["expected_artifacts"]}
    assert "attorney_review_checklist.md" in names


def test_phase8_smb_verticals_are_plan_only_with_owner_signoff() -> None:
    for wf in SMB_VERTICAL_WORKFLOWS:
        payload = _run(wf)
        safety = payload["safety"]
        assert safety["mode"] == "plan_only"
        assert safety["auto_side_effects_enabled"] is False
        assert safety["requires_owner_signoff"] is True
        assert safety["external_systems_mutated"] is False
        steps = {s.get("step") for s in payload["tool_call_sequence"]}
        assert "intake" in steps
        assert "quality_gate" in steps
        assert "draft_only_safety" in steps


def test_phase8_dispatch_prompts_carry_safety_terminal_step() -> None:
    # The last vertical-specific step must be a safety step so the subagent reads
    # the safety instruction last in the dispatch prompt.
    for wf in HRIS_WORKFLOWS + IDP_WORKFLOWS:
        payload = _run(wf)
        last_step = payload["tool_call_sequence"][-1].get("step")
        assert last_step == "signed_intent_safety", f"{wf} last step is {last_step}"
    for wf in LEGAL_WORKFLOWS:
        payload = _run(wf)
        assert payload["tool_call_sequence"][-1].get("step") == "legal_safety"
    for wf in SMB_VERTICAL_WORKFLOWS:
        payload = _run(wf)
        assert payload["tool_call_sequence"][-1].get("step") == "draft_only_safety"


def test_phase8_catalog_lists_all_new_verticals_under_tier_a() -> None:
    payload = json.loads(integrated_project_catalog_tool.invoke({"tier": "A", "max_items": 100}))
    ids = {item["project_id"] for item in payload["projects"]}
    for new_id in [
        "bamboohr-broker", "workday-broker", "gusto-broker",
        "azure-ad-broker", "okta-broker", "google-workspace-broker",
        "employment-contract-blueprint",
        "smb-cs-playbook", "smb-finance-close", "smb-sales-motion", "smb-it-helpdesk-runbook",
    ]:
        assert new_id in ids, f"{new_id} missing from tier-A catalog"


def test_phase8_external_broker_filter_lists_brokers_only() -> None:
    payload = json.loads(integrated_project_catalog_tool.invoke({"integration_mode": "external-broker", "max_items": 100}))
    ids = {item["project_id"] for item in payload["projects"]}
    expected = {
        "bamboohr-broker", "workday-broker", "gusto-broker",
        "azure-ad-broker", "okta-broker", "google-workspace-broker",
    }
    assert expected.issubset(ids)
    # SMB plan-only verticals must NOT appear in external-broker mode
    for plan_only in ["smb-cs-playbook", "smb-finance-close", "employment-contract-blueprint"]:
        assert plan_only not in ids
