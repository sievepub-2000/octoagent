"""Real WebUI + API end-to-end smoke for Skills / MCP / Channels CRUD.

Covers task 4 of 2026-04-23 directive: install/delete skill, add/remove MCP
server, modify/revert channel config — all verified via API and WebUI screenshots.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx

API = "http://127.0.0.1:19802"
WEBUI = "http://127.0.0.1:19800"
OUT = Path(__file__).resolve().parent.parent / "tmp" / "admin_smoke"
OUT.mkdir(parents=True, exist_ok=True)


def log(step: str, payload: object = "") -> None:
    mark = "✓" if "OK" in step or "PASS" in step else "·"
    print(f"[{mark}] {step}: {payload}" if payload != "" else f"[{mark}] {step}")


def skills_cycle(c: httpx.Client) -> dict:
    name = "smoke-admin-test-skill"
    # clean any previous
    c.delete(f"{API}/api/skills/{name}")

    r = c.post(
        f"{API}/api/skills",
        json={
            "name": name,
            "description": "Temporary smoke skill for admin e2e",
            "content": "# Smoke Test Skill\n\nThis skill exists only for verification.",
        },
        timeout=20.0,
    )
    created_ok = r.status_code in (200, 201)
    log("skills.create", f"status={r.status_code}")

    r2 = c.get(f"{API}/api/skills", timeout=15.0)
    items = r2.json() if r2.status_code == 200 else []
    if isinstance(items, dict):
        items = items.get("items") or items.get("skills") or []
    found = any(isinstance(s, dict) and s.get("name") == name for s in items)
    log("skills.verify_present", f"found={found} total={len(items)}")

    r3 = c.delete(f"{API}/api/skills/{name}", timeout=15.0)
    log("skills.delete", f"status={r3.status_code}")

    r4 = c.get(f"{API}/api/skills", timeout=15.0)
    items2 = r4.json() if r4.status_code == 200 else []
    if isinstance(items2, dict):
        items2 = items2.get("items") or items2.get("skills") or []
    gone = not any(isinstance(s, dict) and s.get("name") == name for s in items2)
    log("skills.verify_gone", f"gone={gone}")

    passed = created_ok and found and r3.status_code in (200, 204) and gone
    return {"step": "skills", "passed": passed, "created_ok": created_ok,
            "found": found, "delete_status": r3.status_code, "gone": gone}


def mcp_cycle(c: httpx.Client) -> dict:
    r = c.get(f"{API}/api/mcp/config", timeout=10.0)
    log("mcp.get", f"status={r.status_code}")
    base = r.json() if r.status_code == 200 else {}
    original_servers = dict(base.get("mcp_servers") or {})

    test_key = "smoke-admin-test-mcp"
    updated = dict(original_servers)
    updated[test_key] = {
        "command": "echo",
        "args": ["smoke"],
        "env": {},
    }
    r2 = c.put(f"{API}/api/mcp/config", json={"mcp_servers": updated}, timeout=15.0)
    log("mcp.put_add", f"status={r2.status_code}")

    r3 = c.get(f"{API}/api/mcp/config", timeout=10.0)
    present = test_key in ((r3.json() or {}).get("mcp_servers") or {})
    log("mcp.verify_present", f"present={present}")

    r4 = c.put(f"{API}/api/mcp/config", json={"mcp_servers": original_servers}, timeout=15.0)
    log("mcp.put_revert", f"status={r4.status_code}")

    r5 = c.get(f"{API}/api/mcp/config", timeout=10.0)
    gone = test_key not in ((r5.json() or {}).get("mcp_servers") or {})
    log("mcp.verify_gone", f"gone={gone}")

    passed = r2.status_code == 200 and present and r4.status_code == 200 and gone
    return {"step": "mcp", "passed": passed, "put_add": r2.status_code,
            "present": present, "put_revert": r4.status_code, "gone": gone}


def channels_cycle(c: httpx.Client) -> dict:
    r = c.get(f"{API}/api/channels/", timeout=10.0)
    log("channels.get", f"status={r.status_code}")
    data = r.json() if r.status_code == 200 else {}
    channels = data.get("channels") or {}
    items = list(channels.items()) if isinstance(channels, dict) else []
    if not items:
        return {"step": "channels", "passed": False, "reason": "no channels configured"}

    # pick feishu if available (has 3 required fields we can supply)
    name = "feishu" if "feishu" in channels else items[0][0]
    before_configured = bool(channels.get(name, {}).get("configured"))

    # Fill required fields -> configured should flip True
    add_cfg = {
        "app_id": "smoke-admin-test-app",
        "app_secret": "smoke-admin-test-secret",
        "verification_token": "smoke-admin-test-token",
    }
    r2 = c.put(f"{API}/api/channels/{name}/config", json={"config": add_cfg}, timeout=15.0)
    log(f"channels.put_add({name})", f"status={r2.status_code}")

    r3 = c.get(f"{API}/api/channels/", timeout=10.0)
    after_add = (r3.json().get("channels") or {}).get(name, {})
    configured_after_add = bool(after_add.get("configured"))
    log("channels.verify_configured", f"configured={configured_after_add}")

    # Revert: blank the fields
    revert_cfg = {"app_id": "", "app_secret": "", "verification_token": ""}
    r4 = c.put(f"{API}/api/channels/{name}/config", json={"config": revert_cfg}, timeout=15.0)
    log("channels.put_revert", f"status={r4.status_code}")

    r5 = c.get(f"{API}/api/channels/", timeout=10.0)
    after_revert = (r5.json().get("channels") or {}).get(name, {})
    configured_after_revert = bool(after_revert.get("configured"))
    log("channels.verify_reverted", f"configured={configured_after_revert}")

    passed = (
        r2.status_code == 200
        and configured_after_add
        and r4.status_code == 200
        and not configured_after_revert
    )
    return {
        "step": "channels",
        "passed": passed,
        "target": name,
        "before_configured": before_configured,
        "put_add": r2.status_code,
        "configured_after_add": configured_after_add,
        "put_revert": r4.status_code,
        "configured_after_revert": configured_after_revert,
    }


def run_webui_screenshots() -> dict:
    # Place script inside frontend/ so `require('@playwright/test')` resolves
    script = Path("/home/sieve-pub/public-workspace/octoagent/frontend/.admin-smoke-shot.cjs")
    script.write_text(
        """
const { chromium } = require("@playwright/test");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }});
  const page = await ctx.newPage();
  const base = process.env.WEBUI || 'http://127.0.0.1:19800';
  const out = process.env.OUT || '""" + str(OUT) + """';
  const pages = [
    ['skills', '/workspace/config/skills'],
    ['mcp', '/workspace/config/mcp'],
    ['channels', '/workspace/config/channels'],
  ];
  const results = {};
  for (const [label, path] of pages) {
    try {
      const resp = await page.goto(base + path, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForTimeout(1500);
      const shot = out + '/webui_' + label + '.png';
      await page.screenshot({ path: shot, fullPage: false });
      results[label] = { status: resp?.status() || 0, shot };
    } catch (e) {
      results[label] = { error: String(e) };
    }
  }
  console.log(JSON.stringify(results));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
""",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["pnpm", "exec", "node", str(script)],
        cwd="/home/sieve-pub/public-workspace/octoagent/frontend",
        capture_output=True,
        text=True,
        timeout=120,
    )
    try:
        parsed = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        parsed = {"raw_stdout": proc.stdout, "raw_stderr": proc.stderr}
    return parsed


def main() -> int:
    with httpx.Client() as c:
        r = c.get(f"{API}/health", timeout=5.0)
        log("gateway.health", r.json() if r.status_code == 200 else r.status_code)

        skills = skills_cycle(c)
        mcp = mcp_cycle(c)
        channels = channels_cycle(c)

    shots = run_webui_screenshots()

    report = {
        "skills": skills,
        "mcp": mcp,
        "channels": channels,
        "webui_screenshots": shots,
        "summary": {
            "skills_passed": skills.get("passed"),
            "mcp_passed": mcp.get("passed"),
            "channels_passed": channels.get("passed"),
            "webui_ok": all(
                (v.get("status") or 0) == 200
                for v in shots.values() if isinstance(v, dict)
            ) if isinstance(shots, dict) else False,
        },
    }
    out_file = OUT / "admin_smoke_report.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n=== REPORT ===")
    print(json.dumps(report["summary"], indent=2))
    print(f"full report: {out_file}")
    all_passed = all([skills.get("passed"), mcp.get("passed"), channels.get("passed")])
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
