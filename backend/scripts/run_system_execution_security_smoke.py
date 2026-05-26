"""Smoke-check operator auth on system-execution mutating routes."""

# ruff: noqa: E402, I001

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


PROTECTED_REQUESTS = [
    (
        "PUT",
        "/api/system-execution/config",
        "admin",
        {
            "enabled": False,
            "engine": "none",
            "permission_policy": {
                "policy_id": "smoke",
                "title": "Smoke",
                "default_effect": "ask",
                "rules": [],
            },
        },
    ),
    (
        "POST",
        "/api/system-execution/sessions/live",
        "operator",
        {"goal": "security smoke", "target": "workspace_cli", "requested_commands": ["pwd"]},
    ),
    (
        "POST",
        "/api/system-execution/cli/workspace",
        "operator",
        {"command": "pwd", "require_approval": True, "role": "operator"},
    ),
    (
        "POST",
        "/api/system-execution/cli/system",
        "admin",
        {"command": "pwd", "require_approval": True, "role": "operator"},
    ),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args()


def main() -> int:
    _parse_args()
    from fastapi.testclient import TestClient

    from src.runtime.config.app_config import AppConfig
    from src.gateway.app import create_app

    previous = os.environ.get("OCTO_OPERATOR_TOKEN")
    config_path = AppConfig.resolve_config_path()
    previous_config = config_path.read_text(encoding="utf-8") if config_path.exists() else None
    os.environ["OCTO_OPERATOR_TOKEN"] = "system-execution-smoke-token"
    try:
        client = TestClient(create_app())
        for method, path, minimum_role, payload in PROTECTED_REQUESTS:
            response = client.request(method, path, json=payload)
            if response.status_code != 403:
                raise SystemExit(f"{method} {path} expected 403 without operator token, got {response.status_code}: {response.text}")
            allowed = client.request(
                method,
                path,
                json=payload,
                headers={"X-OctoAgent-Operator-Token": "system-execution-smoke-token", "X-OctoAgent-Operator-Role": minimum_role},
            )
            if allowed.status_code >= 500:
                raise SystemExit(f"{method} {path} returned server error with operator token: {allowed.status_code}: {allowed.text}")
    finally:
        if previous is None:
            os.environ.pop("OCTO_OPERATOR_TOKEN", None)
        else:
            os.environ["OCTO_OPERATOR_TOKEN"] = previous
        if previous_config is not None:
            config_path.write_text(previous_config, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
