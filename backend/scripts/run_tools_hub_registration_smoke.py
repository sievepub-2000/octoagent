"""Verify Tools Hub can register and unregister a custom skill/tool."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass
class ToolsHubRegistrationReport:
    ok: bool = True
    gateway_url: str = ""
    skill_name: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)


def _registry_contains(payload: dict[str, Any], skill_name: str) -> bool:
    return any(item.get("name") == skill_name for item in payload.get("skills", []) if isinstance(item, dict))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _snapshot_generated_agent_docs() -> tuple[Path, str | None]:
    path = _repo_root() / ".github" / "copilot-instructions.md"
    if not path.exists():
        return path, None
    return path, path.read_text(encoding="utf-8")


def _restore_generated_agent_docs(snapshot: tuple[Path, str | None]) -> None:
    path, content = snapshot
    if content is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run(*, gateway_url: str) -> ToolsHubRegistrationReport:
    snapshot = _snapshot_generated_agent_docs()
    try:
        if not gateway_url or gateway_url == "testclient":
            return run_local_contract()
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
    finally:
        _restore_generated_agent_docs(snapshot)


def run_local_contract() -> ToolsHubRegistrationReport:
    from src.gateway.app import create_app

    report = ToolsHubRegistrationReport(gateway_url="testclient")
    skill_name = f"tools-hub-check-{uuid.uuid4().hex[:8]}"
    report.skill_name = skill_name
    client = TestClient(create_app())
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
    parser.add_argument("--gateway-url", default="", help="Gateway URL, or empty/testclient for in-process FastAPI smoke.")
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
