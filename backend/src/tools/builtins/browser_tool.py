"""Single model-facing browser tool backed exclusively by Patchright."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from langchain_core.tools import tool

from src.runtime.config.paths import get_paths
from src.tools.sandbox.browser.execution import EmbeddedHeadlessProvider, _run_browser_call
from src.utils.url_safety import is_url_safe


def _run_browser(url: str, actions: list[dict[str, Any]], timeout_seconds: int) -> dict[str, Any]:
    provider = EmbeddedHeadlessProvider()
    if not provider.enabled or provider.engine != "patchright":
        raise RuntimeError("Patchright browser is not enabled")
    if not is_url_safe(url):
        raise ValueError("URL must resolve to a public HTTP(S) address")

    sync_playwright = provider._sync_playwright()
    results: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**provider._launch_kwargs())
        try:
            page = browser.new_page(viewport={"width": 1365, "height": 900})
            safety_cache: dict[str, bool] = {}

            def guard(route) -> None:
                request_url = route.request.url
                scheme = urlparse(request_url).scheme
                allowed = safety_cache.setdefault(request_url, is_url_safe(request_url)) if scheme in {"http", "https"} else False
                if scheme in {"data", "blob", "about"} or allowed:
                    route.continue_()
                else:
                    route.abort()

            page.route("**/*", guard)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            for index, raw in enumerate(actions):
                action = str(raw.get("action") or "snapshot").strip().lower()
                target = str(raw.get("target") or raw.get("selector") or "").strip()
                value = str(raw.get("value") or "")
                if action == "click":
                    if not target:
                        raise ValueError("click requires a CSS selector in target")
                    page.locator(target).first.click(timeout=timeout_seconds * 1000)
                elif action == "fill":
                    if not target:
                        raise ValueError("fill requires a CSS selector in target")
                    page.locator(target).first.fill(value, timeout=timeout_seconds * 1000)
                elif action == "evaluate":
                    script = value or target or "document.title"
                    results.append({"index": index, "action": action, "result": str(page.evaluate(script))[:2000]})
                    continue
                elif action == "wait":
                    if target:
                        page.locator(target).first.wait_for(timeout=timeout_seconds * 1000)
                    else:
                        page.wait_for_timeout(min(max(int(value or "1000"), 0), 30_000))
                elif action == "screenshot":
                    root = get_paths().browser_runtime_dir / "artifacts"
                    root.mkdir(parents=True, exist_ok=True)
                    path = root / f"browser-{len(list(root.glob('browser-*.png'))) + 1:06d}.png"
                    page.screenshot(path=str(path), full_page=True)
                    results.append({"index": index, "action": action, "artifact_path": str(path)})
                    continue
                elif action != "snapshot":
                    raise ValueError(f"unsupported browser action: {action}")
                results.append({"index": index, "action": action, "url": page.url, "title": page.title()})

            body_text = page.locator("body").inner_text(timeout=timeout_seconds * 1000)[:8000]
            links = page.eval_on_selector_all("a[href]", "els => els.slice(0, 100).map(e => ({text: (e.innerText || '').trim().slice(0, 160), url: e.href}))")
            return {
                "status": "ok",
                "engine": "patchright",
                "url": page.url,
                "title": page.title(),
                "text": body_text,
                "links": links,
                "actions": results,
            }
        finally:
            browser.close()


@tool("browser", parse_docstring=True)
def browser_tool(
    url: str,
    actions: list[dict[str, Any]] | None = None,
    timeout_seconds: int = 20,
) -> str:
    """Open and interact with a public web page using the Patchright browser.

    Args:
        url: Public HTTP(S) page to open.
        actions: Ordered actions. Each item uses action snapshot, click, fill,
            evaluate, wait, or screenshot; target is a CSS selector and value
            is fill text, JavaScript, or wait milliseconds.
        timeout_seconds: Per-navigation/action timeout from 5 to 60 seconds.
    """
    safe_timeout = min(max(int(timeout_seconds), 5), 60)
    try:
        payload = _run_browser_call(lambda: _run_browser(url, actions or [{"action": "snapshot"}], safe_timeout))
    except Exception as exc:  # noqa: BLE001 - tool boundary returns structured failure
        payload = {"status": "error", "engine": "patchright", "error": str(exc)}
    return json.dumps(payload, ensure_ascii=False)
