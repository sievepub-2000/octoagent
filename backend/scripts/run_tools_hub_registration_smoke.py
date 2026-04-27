"""Verify Tools Hub can register and unregister a custom skill/tool."""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx


@dataclass
class ToolsHubRegistrationReport:
    ok: bool = True
    gateway_url: str = ""
    skill_name: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)


def _registry_contains(payload: dict[str, Any], skill_name: str) -> bool:
    return any(item.get("name") == skill_name for item in payload.get("skills", []) if isinstance(item, dict))


def run(*, gateway_url: str) -> ToolsHubRegistrationReport:
    report = ToolsHubRegistrationReport(gateway_url=gateway_url.rstrip("/"))
    skill_name = f"tools-hub-check-{uuid.uuid4().hex[:8]}"
    report.skill_name = skill_name
    with httpx.Client(base_url=report.gateway_url, timeout=20, trust_env=False) as client:
        created = client.post(
            "/api/skills",
            json={
                "name": skill_name,
                "description": "Temporary Tools Hub registration smoke skill.",
                "content": "Use only to verify that Tools Hub registration and unregistration are healthy.",
            },
        )
        created.raise_for_status()
        report.checks.append({"id": "skill-created", "skill": created.json()})

        registered = client.get("/api/tools/registry")
        registered.raise_for_status()
        registered_payload = registered.json()
        if not _registry_contains(registered_payload, skill_name):
            raise AssertionError(f"Tools registry did not include {skill_name}")
        report.checks.append({"id": "registry-includes-skill", "skills_total": registered_payload.get("summary", {}).get("skills_total")})

        deleted = client.delete(f"/api/skills/{skill_name}")
        deleted.raise_for_status()
        report.checks.append({"id": "skill-deleted", "payload": deleted.json()})

        unregistered = client.get("/api/tools/registry")
        unregistered.raise_for_status()
        unregistered_payload = unregistered.json()
        if _registry_contains(unregistered_payload, skill_name):
            raise AssertionError(f"Tools registry still included deleted skill {skill_name}")
        report.checks.append({"id": "registry-removes-skill", "skills_total": unregistered_payload.get("summary", {}).get("skills_total")})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-url", default="http://127.0.0.1:19880")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = run(gateway_url=args.gateway_url)
    except Exception as exc:
        report = ToolsHubRegistrationReport(ok=False, gateway_url=args.gateway_url, checks=[{"id": "tools-hub-registration", "error": str(exc)}])
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2 if args.json else None))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
