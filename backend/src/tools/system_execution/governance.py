"""Harness/Warp-style governance for system operation execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.agents.core.instruction_contracts import detect_instruction_contract
from src.governance.operator import signed_audit_event


@dataclass(frozen=True)
class SystemOperationGovernanceDecision:
    allowed: bool
    risk_level: str
    requires_confirmation: bool
    guardrails: tuple[str, ...]
    reason: str
    audit_event: dict[str, Any]


def evaluate_system_operation_governance(
    *,
    command: str,
    require_approval: bool,
    actor: str | None = None,
    role: str | None = None,
) -> SystemOperationGovernanceDecision:
    """Evaluate whether a command can run without an approval gate."""

    contract = detect_instruction_contract(command)
    requires_confirmation = contract.requires_confirmation or contract.risk_level == "high"
    allowed = not requires_confirmation or require_approval
    reason = "approved_by_request" if allowed else "operator_confirmation_required"
    audit_event = signed_audit_event(
        "system_operation.governance_evaluated",
        actor=actor,
        role=role,
        command=command,
        require_approval=require_approval,
        intent=contract.intent,
        risk_level=contract.risk_level,
        requires_confirmation=requires_confirmation,
        guardrails=list(contract.guardrails),
        allowed=allowed,
        reason=reason,
    )
    return SystemOperationGovernanceDecision(
        allowed=allowed,
        risk_level=contract.risk_level,
        requires_confirmation=requires_confirmation,
        guardrails=contract.guardrails,
        reason=reason,
        audit_event=audit_event,
    )


__all__ = [
    "SystemOperationGovernanceDecision",
    "evaluate_system_operation_governance",
]
