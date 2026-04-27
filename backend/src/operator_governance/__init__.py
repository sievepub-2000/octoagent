"""Shared operator authorization, confirmation, redaction, and signed audit helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from datetime import UTC, datetime
from typing import Any

SECRET_KEYS = ("token", "secret", "password", "key", "credential", "authorization")
SECRET_VALUE_RE = re.compile(r"(?i)(bearer|token|secret|password|api[_-]?key)=([A-Za-z0-9._~:/+=-]{6,})")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def operator_identity(actor: str | None = None, role: str | None = None) -> dict[str, str]:
    return {
        "actor": (actor or os.getenv("OCTO_OPERATOR_ACTOR") or "operator").strip() or "operator",
        "role": (role or os.getenv("OCTO_OPERATOR_ROLE") or "operator").strip() or "operator",
    }


def has_operator_role(role: str | None, *, minimum: str = "operator") -> bool:
    order = {"viewer": 0, "operator": 1, "admin": 2}
    return order.get((role or "operator").strip().lower(), 1) >= order.get(minimum, 1)


def token_matches_env(env_name: str, provided: str | None) -> bool:
    """Return true when the optional shared-secret env token is absent or matches."""
    expected = os.getenv(env_name, "").strip()
    if not expected:
        return True
    return hmac.compare_digest((provided or "").strip(), expected)


def require_operator_access(
    *,
    role: str | None = None,
    token: str | None = None,
    minimum: str = "operator",
    token_env: str = "OCTO_OPERATOR_TOKEN",
) -> None:
    """Raise ValueError when the caller lacks the configured operator role/token."""
    if not has_operator_role(role, minimum=minimum):
        raise ValueError(f"Operator role '{minimum}' required")
    if not token_matches_env(token_env, token):
        raise ValueError("Invalid operator token")


def confirmation_matches(action: str, confirmation: str | None) -> bool:
    expected = f"CONFIRM {action}".strip().upper()
    return (confirmation or "").strip().upper() == expected


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if any(marker in str(key).lower() for marker in SECRET_KEYS):
                redacted[str(key)] = "***REDACTED***"
            else:
                redacted[str(key)] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}=***REDACTED***", value)
    return value


def sign_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(redact_secrets(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    secret = os.getenv("OCTO_OPERATOR_AUDIT_SECRET", "").encode("utf-8")
    if secret:
        return hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def signed_audit_event(event: str, *, actor: str | None = None, role: str | None = None, **details: Any) -> dict[str, Any]:
    identity = operator_identity(actor, role)
    payload = {
        "event": event,
        "created_at": utc_now(),
        "actor": identity["actor"],
        "role": identity["role"],
        "details": redact_secrets(details),
    }
    payload["signature_algorithm"] = "hmac-sha256" if os.getenv("OCTO_OPERATOR_AUDIT_SECRET") else "sha256"
    payload["signature"] = sign_payload(payload)
    return payload
