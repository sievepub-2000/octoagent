#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

BASE_URL = os.getenv("OCTO_WEBUI_BASE_URL", "http://127.0.0.1:19880")
SCREENSHOT_DIR = Path(__file__).resolve().parents[1] / "screenshots" / "webui-installs"
RESULT_FILE = SCREENSHOT_DIR / "install-results.json"


def fetch_text(url: str, timeout: int = 20) -> str:
    with urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8")


def fetch_json(url: str, timeout: int = 20) -> dict:
    return json.loads(fetch_text(url, timeout=timeout))


def browser_use_content() -> str:
    return """# Browser Use

Source repository: https://github.com/browser-use/browser-use
Official skill path: https://github.com/browser-use/browser-use/tree/main/skills/browser-use

Use this skill when the task requires browser automation, interactive website workflows, page inspection, navigation, form submission, extraction from rendered pages, or browser-based end-to-end task execution.

## Guidance

- Prefer browser automation when static HTTP fetching is insufficient.
- Use it for login-gated flows, dynamic rendering, form interactions, multi-step navigation, and UI verification.
- Capture evidence with screenshots when the result depends on rendered UI state.
- Keep runs scoped and goal-oriented to avoid unnecessary browsing.
"""


def karpathy_autoresearch_content() -> str:
    program = fetch_text("https://raw.githubusercontent.com/karpathy/autoresearch/master/program.md")
    return """# Karpathy Autoresearch

This skill wraps the core operating model from karpathy/autoresearch and adapts it to OctoAgent workflows.

Source repository: https://github.com/karpathy/autoresearch

## Intent

- Use a measurable metric and keep an experiment log.
- Establish a baseline before edits.
- Keep or discard changes based on measured outcomes.
- Run autonomously once the experiment loop begins.

## Original program.md

""" + program


def prompts_chat_content() -> str:
    return """# Awesome ChatGPT Prompt Library

Source repository: https://github.com/f/prompts.chat
Website: https://prompts.chat/

Use this skill when the user wants inspiration, reusable prompt patterns, prompt-library discovery, or prompt examples for a specific task.

## What it provides

- A large open prompt library originally known as Awesome ChatGPT Prompts.
- Searchable prompts covering writing, coding, research, ideation, education, and productivity.
- A prompt-engineering knowledge base that works across modern AI assistants.

## How to use

1. Identify the task domain and desired output format.
2. Search prompts.chat or the prompts.chat MCP server for a matching prompt family.
3. Adapt the prompt to the user's context instead of copying blindly.
4. Preserve safety, privacy, and project-specific constraints.

## Recommended integrations

- prompts.chat MCP server: https://prompts.chat/api/mcp
- Project repo: https://github.com/f/prompts.chat
"""


def remotion_content() -> str:
    return """# Remotion Skills

Source listing: https://skills.sh/remotion-dev/skills/remotion-best-practices
Source repo: https://github.com/remotion-dev/skills

Use this skill when working with Remotion video code, composition setup, animation timing, captions, FFmpeg workflows, subtitles, audio visualization, and rendering checks.

## Key guidance

- Scaffold with `npx create-video@latest --yes --blank --no-tailwind my-video` for new projects.
- Preview with `npx remotion studio`.
- Run a one-frame render sanity check with `npx remotion still [composition-id] --scale=0.25 --frame=30`.
- Load deeper rule files for subtitles, FFmpeg, silence detection, audio visualization, sound effects, and transitions.
"""


SKILLS_TO_CREATE = [
    {
        "name": "browser-use",
        "description": "Official browser-use skill for AI-assisted browser automation.",
        "license": "MIT",
        "content": browser_use_content,
    },
    {
        "name": "karpathy-autoresearch",
        "description": "Autonomous experimentation workflow adapted from karpathy/autoresearch.",
        "license": "MIT",
        "content": karpathy_autoresearch_content,
    },
    {
        "name": "awesome-chatgpt-prompt",
        "description": "Prompt-library skill wrapper for prompts.chat, formerly Awesome ChatGPT Prompts.",
        "license": "MIT",
        "content": prompts_chat_content,
    },
    {
        "name": "remotion-skills",
        "description": "Remotion best-practices guidance sourced from skills.sh/remotion-dev/skills.",
        "license": "",
        "content": remotion_content,
    },
]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def set_input(page: Page, placeholder: str, value: str) -> None:
    locator = page.get_by_placeholder(placeholder)
    locator.fill(value)


def create_skill(page: Page, item: dict[str, object], results: list[dict[str, str]]) -> None:
    page.goto(f"{BASE_URL}/workspace/config/skills", wait_until="networkidle", timeout=30000)
    skills_json = fetch_json(f"{BASE_URL}/api/skills")
    if any(skill.get("name") == item["name"] for skill in skills_json.get("skills", [])):
        results.append({"type": "skill", "name": str(item["name"]), "status": "already-present"})
        return

    set_input(page, "my-custom-skill", str(item["name"]))
    set_input(page, "MIT", str(item["license"]))
    page.get_by_placeholder("What does this skill do?").fill(str(item["description"]))
    content = item["content"]() if callable(item["content"]) else str(item["content"])
    page.get_by_placeholder("Additional instructions...").fill(content)
    page.get_by_role("button", name="Create skill").click()
    page.wait_for_timeout(1500)
    skills_json = fetch_json(f"{BASE_URL}/api/skills")
    status = "installed" if any(skill.get("name") == item["name"] for skill in skills_json.get("skills", [])) else "create-submitted"
    results.append({"type": "skill", "name": str(item["name"]), "status": status})


def reinstall_plugin(page: Page, plugin_id: str, display_name: str, results: list[dict[str, str]]) -> None:
    page.goto(f"{BASE_URL}/workspace/config/plugins", wait_until="networkidle", timeout=30000)
    page.get_by_placeholder("e.g. code-review").fill(plugin_id)
    page.locator("button").filter(has_text="Install").first.click()
    page.wait_for_timeout(1500)
    registry = fetch_json(f"{BASE_URL}/api/plugins/registry")
    status = "reinstalled" if any(entry.get("plugin_id") == plugin_id for entry in registry.get("entries", [])) else "install-submitted"
    results.append({"type": "plugin", "name": plugin_id, "status": status})


def add_mcp_server(page: Page, results: list[dict[str, str]]) -> None:
    page.goto(f"{BASE_URL}/workspace/config/mcp", wait_until="networkidle", timeout=30000)
    mcp_config = fetch_json(f"{BASE_URL}/api/mcp/config")
    if "prompts-chat" in (mcp_config.get("mcp_servers") or {}):
        results.append({"type": "mcp", "name": "prompts-chat", "status": "already-present"})
        return

    set_input(page, "my-mcp-server", "prompts-chat")
    set_input(page, "Optional description", "Remote prompts.chat MCP server from f/prompts.chat")
    page.get_by_role("button", name="HTTP").click()
    set_input(page, "http://localhost:3000/sse", "https://prompts.chat/api/mcp")
    page.get_by_role("button", name="Add server").click()
    page.wait_for_timeout(1500)
    mcp_config = fetch_json(f"{BASE_URL}/api/mcp/config")
    status = "installed" if "prompts-chat" in (mcp_config.get("mcp_servers") or {}) else "add-submitted"
    results.append({"type": "mcp", "name": "prompts-chat", "status": status})


def main() -> int:
    ensure_dir(SCREENSHOT_DIR)
    results: list[dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})

        for item in SKILLS_TO_CREATE:
            create_skill(page, item, results)
        page.screenshot(path=str(SCREENSHOT_DIR / "skills-page.png"), full_page=True)

        reinstall_plugin(page, "workspace-runtime-bridge", "Workspace Runtime Bridge", results)
        page.goto(f"{BASE_URL}/workspace/config/plugins", wait_until="networkidle", timeout=30000)
        page.screenshot(path=str(SCREENSHOT_DIR / "plugins-page.png"), full_page=True)

        add_mcp_server(page, results)
        page.goto(f"{BASE_URL}/workspace/config/mcp", wait_until="networkidle", timeout=30000)
        page.screenshot(path=str(SCREENSHOT_DIR / "mcp-page.png"), full_page=True)

        browser.close()

    RESULT_FILE.write_text(json.dumps({"base_url": BASE_URL, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "result_file": str(RESULT_FILE), "results": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())