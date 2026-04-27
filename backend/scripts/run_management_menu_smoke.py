"""Smoke-test authenticated WebUI management routes and config APIs."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass
class ManagementSmokeReport:
    ok: bool = True
    auth: dict[str, Any] = field(default_factory=dict)
    api_checks: list[dict[str, Any]] = field(default_factory=list)
    route_checks: list[dict[str, Any]] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", default="http://127.0.0.1:19880")
    parser.add_argument("--gateway-url", default="http://127.0.0.1:19880")
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _create_user() -> tuple[str, str, str, str]:
    from src.user_accounts import get_user_account_store

    store = get_user_account_store()
    username = f"mgmtsmoke{uuid.uuid4().hex[:8]}"
    password = "Passw0rd!123"
    email = f"{username}@example.test"
    fingerprint = "management-smoke-" + uuid.uuid4().hex
    challenge = store.start_registration(username=username, password=password, email=email, display_name="Management Smoke")
    code = challenge.get("dev_code")
    if not code:
        # Local smoke must not depend on SMTP delivery. Read the code only when the
        # dev flag was enabled by the caller; otherwise fall back to password login
        # after direct store verification is impossible.
        raise RuntimeError("OCTO_AUTH_DEV_EXPOSE_CODES=1 is required for management smoke user setup")
    store.verify_registration(challenge_id=challenge["challenge_id"], code=code, device_fingerprint=fingerprint)
    return username, password, email, fingerprint


def _api_check(client: httpx.Client, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = client.request(method, url, **kwargs)
        ok = 200 <= response.status_code < 400
        return {"method": method, "url": url, "status_code": response.status_code, "ok": ok}
    except Exception as exc:
        return {"method": method, "url": url, "status_code": None, "ok": False, "error": str(exc)}


def main() -> int:
    args = _parse_args()
    report = ManagementSmokeReport()
    timeout_ms = int(args.timeout_seconds * 1000)
    username, password, email, fingerprint = _create_user()

    with httpx.Client(timeout=args.timeout_seconds, trust_env=False) as client:
        login = client.post(
            f"{args.gateway_url}/api/auth/login",
            json={"username": username, "password": password, "device_fingerprint": fingerprint},
        )
        login.raise_for_status()
        session = login.json()
        headers = {
            "X-OctoAgent-Session-Token": session["session_token"],
            "X-Tenant-ID": session["tenant_id"],
        }
        report.auth = {"username": username, "email": email, "tenant_id": session["tenant_id"]}

        endpoints = [
            ("GET", "/api/auth/me", {"headers": headers}),
            ("GET", "/api/models", {"headers": headers}),
            ("GET", "/api/bootstrap/status", {"headers": headers}),
            ("GET", "/api/mcp/config", {"headers": headers}),
            ("GET", "/api/plugins/registry", {"headers": headers}),
            ("GET", "/api/plugins/manifests", {"headers": headers}),
            ("GET", "/api/skills", {"headers": headers}),
            ("GET", "/api/tools/registry", {"headers": headers}),
            ("GET", "/api/channels/", {"headers": headers}),
            ("GET", "/api/memory/system/stats", {"headers": headers}),
            ("GET", "/api/skill-evolution/config", {"headers": headers}),
            ("GET", "/api/metrics/memory-health", {"headers": headers}),
            ("GET", "/api/tenants", {"headers": headers}),
            ("GET", "/api/execution-nodes", {"headers": headers}),
        ]
        for method, path, kwargs in endpoints:
            item = _api_check(client, method, f"{args.gateway_url}{path}", **kwargs)
            report.api_checks.append(item)
            report.ok = report.ok and item["ok"]

    routes = [
        "/auth/register",
        "/workspace/chats/new?mock=true",
        "/workspace/agents",
        "/workspace/agents/new",
        "/workspace/workflows",
        "/workspace/tasks",
        "/workspace/config/models",
        "/workspace/config/mcp",
        "/workspace/config/plugins",
        "/workspace/config/skills",
        "/workspace/config/tools",
        "/workspace/config/channels",
        "/workspace/config/memory",
        "/workspace/config/evolution",
        "/workspace/chats/new?settings=overview&mock=true",
        "/workspace/chats/new?settings=bootstrap&mock=true",
        "/workspace/chats/new?settings=runtime-health&mock=true",
        "/workspace/chats/new?settings=system-execution&mock=true",
        "/workspace/chats/new?settings=memory&mock=true",
        "/workspace/chats/new?settings=hooks&mock=true",
        "/workspace/chats/new?settings=update&mock=true",
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        def record_console_error(msg) -> None:
            text = msg.text
            known_benign = "409 (Conflict)" in text
            if msg.type in {"error"} and not known_benign:
                report.console_errors.append(text)

        page.on("console", record_console_error)
        page.on("pageerror", lambda exc: report.page_errors.append(str(exc)))
        page.goto(f"{args.frontend_url}/auth/register", wait_until="domcontentloaded", timeout=timeout_ms)
        page.evaluate(
            """session => {
                localStorage.setItem('octoagent_session_token', session.session_token);
                localStorage.setItem('octoagent_tenant_id', session.tenant_id);
                localStorage.setItem('octoagent_username', session.username);
                localStorage.setItem('octoagent_user_id', session.user_id);
            }""",
            session,
        )
        for route in routes:
            url = f"{args.frontend_url}{route}"
            result: dict[str, Any] = {"route": route, "ok": True}
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.locator("body").wait_for(timeout=timeout_ms)
                body = page.locator("body").inner_text(timeout=5000)
                lowered = body.lower()
                bad_markers = ["runtime error", "application error", "not found", "internal server error"]
                marker = next((item for item in bad_markers if item in lowered), None)
                if marker:
                    result.update({"ok": False, "error": f"marker visible: {marker}", "preview": " ".join(body.split())[:240]})
            except PlaywrightTimeoutError as exc:
                result.update({"ok": False, "error": f"timeout: {exc}"})
            except Exception as exc:
                result.update({"ok": False, "error": str(exc)})
            report.route_checks.append(result)
            report.ok = report.ok and result["ok"]
        context.close()
        browser.close()

    report.ok = report.ok and not report.page_errors and not report.console_errors
    payload = asdict(report)
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.json else None))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
