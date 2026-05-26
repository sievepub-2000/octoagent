from __future__ import annotations

import json

from langchain_core.tools import tool

from src.storage.self_evolution import ChangeType


@tool("propose_self_evolution", parse_docstring=True)
def propose_self_evolution_tool(
    change_type: ChangeType,
    title: str,
    description: str,
    proposed_change_json: str,
    current_value_json: str = "{}",
    tags_csv: str = "",
) -> str:
    """Create a governed self-evolution proposal without changing live behavior.

    Use this after finding a repeatable improvement opportunity. This tool only
    records a proposal; shadow runs, validation, approval, and promotion remain
    separate governed steps.

    Args:
        change_type: Change type such as tool_config, memory_policy, skill_config, or brain_policy.
        title: Short proposal title.
        description: Concrete rationale and expected benefit.
        proposed_change_json: JSON object describing the proposed change.
        current_value_json: JSON object describing current value or evidence.
        tags_csv: Optional comma-separated tags.
    """

    from src.storage.self_evolution import get_self_evolution_service

    try:
        proposed_change = json.loads(proposed_change_json or "{}")
        current_value = json.loads(current_value_json or "{}")
    except json.JSONDecodeError as exc:
        return f"Error: invalid JSON payload: {exc}"
    if not isinstance(proposed_change, dict) or not isinstance(current_value, dict):
        return "Error: proposed_change_json and current_value_json must decode to JSON objects."

    proposal = get_self_evolution_service().create_proposal(
        change_type=change_type,
        title=title.strip()[:160],
        description=description.strip(),
        proposed_change=proposed_change,
        current_value=current_value,
        source="agent",
        tags=[tag.strip() for tag in tags_csv.split(",") if tag.strip()],
    )
    payload = {
        "proposal_id": proposal.proposal_id,
        "status": proposal.status.value,
        "change_type": proposal.change_type,
        "title": proposal.title,
        "next_steps": ["start_shadow_run", "validate", "operator_approve", "promote"],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
