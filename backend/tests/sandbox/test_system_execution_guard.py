"""System-execution governance guard.

`evaluate_system_operation_governance` is the synchronous gate that
decides whether a shell-style command can run without explicit operator
approval. The invariants below codify the safety contract:

* A read-only command (`ls`, `cat`) must NOT require confirmation.
* Any command tagged as "system operation" (sudo, rm -rf, chmod, chown,
  etc.) MUST require confirmation when `require_approval=False`.
* A high-risk command paired with an explicit `require_approval=True`
  is allowed (operator-attested execution path).
* The returned governance decision is immutable (frozen dataclass) and
  always carries a signed audit event.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.tools.system_execution.governance import (
    evaluate_system_operation_governance,
)


def test_safe_command_is_allowed_without_confirmation():
    decision = evaluate_system_operation_governance(
        command="ls -la /tmp",
        require_approval=False,
    )
    assert decision.allowed is True
    assert decision.requires_confirmation is False
    assert decision.risk_level in {"low", "medium"}


def test_dangerous_command_blocked_without_approval():
    """A destructive command must be blocked when the caller has NOT
    presented operator approval. This is the core sandbox safety gate."""
    decision = evaluate_system_operation_governance(
        command="sudo rm -rf /home/user/data",
        require_approval=False,
    )
    assert decision.requires_confirmation is True
    assert decision.allowed is False
    assert decision.reason == "operator_confirmation_required"


def test_dangerous_command_allowed_with_explicit_approval():
    """Same dangerous command, but `require_approval=True` simulates the
    operator having confirmed in the WebUI."""
    decision = evaluate_system_operation_governance(
        command="sudo rm -rf /home/user/data",
        require_approval=True,
        actor="operator-1",
        role="admin",
    )
    assert decision.allowed is True
    assert decision.reason == "approved_by_request"


def test_decision_is_frozen():
    decision = evaluate_system_operation_governance(
        command="ls",
        require_approval=False,
    )
    assert dataclasses.is_dataclass(decision)
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.allowed = not decision.allowed  # type: ignore[misc]


def test_audit_event_records_actor_and_outcome(monkeypatch):
    """Every decision must produce a signed audit event recording who
    asked for what and whether it was allowed — this is the audit trail
    the operator console reads."""
    monkeypatch.setenv("OCTO_OPERATOR_AUDIT_SECRET", "test-only-audit-secret")
    decision = evaluate_system_operation_governance(
        command="sudo systemctl restart nginx",
        require_approval=True,
        actor="alice",
        role="operator",
    )
    event = decision.audit_event
    assert isinstance(event, dict)
    assert event.get("event") == "system_operation.governance_evaluated"
    # `signed_audit_event` puts actor/role at the top level and the
    # operation payload under `details`.
    assert event.get("actor") == "alice"
    assert event.get("role") == "operator"
    assert event.get("signature_algorithm") == "hmac-sha256"
    assert isinstance(event.get("signature"), str) and event["signature"]
    details = event.get("details") or {}
    assert details.get("command") == "sudo systemctl restart nginx"
    assert details.get("allowed") is True


def test_guardrails_are_tuple_so_callers_cannot_mutate():
    """Returning a list would let downstream callers mutate the guard
    list and weaken the contract retroactively. A tuple makes this safe."""
    decision = evaluate_system_operation_governance(
        command="chmod 777 /etc/shadow",
        require_approval=False,
    )
    assert isinstance(decision.guardrails, tuple)
