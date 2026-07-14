"""Browser regression checks for the chat shell and input controls."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

DEFAULT_FRONTEND_URL = "http://127.0.0.1:19800"


def _browser_launch_options(playwright) -> dict[str, object]:
    candidates = [
        os.environ.get("OCTOPUSAGENT_BROWSER_PATH"),
        playwright.chromium.executable_path,
        shutil.which("chromium-browser"),
        shutil.which("chromium"),
        shutil.which("google-chrome"),
    ]
    executable = next(
        (candidate for candidate in candidates if candidate and os.path.exists(candidate)),
        None,
    )

    options: dict[str, object] = {"headless": True}
    if executable:
        options["executable_path"] = executable
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        options["args"] = ["--no-sandbox"]
    return options


@dataclass
class ChatRegressionResult:
    welcome_copy_normalized: bool = False
    attachment_button_stable: bool = False
    stale_thread_shell_restored: bool = False
    continuation_shell_ready: bool = False
    existing_thread_route_stable: bool = False
    ordinary_tool_history_stable: bool = False
    web_tool_chain_history_stable: bool = False
    context_guard_notice_visible: bool = False
    multi_turn_history_stable: bool = False
    continuation_history_stable: bool = False
    long_scroll_message_count: int = 520
    long_scroll_render_ms: int | None = None
    long_scroll_stable: bool = False
    critical_browser_errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real-browser chat regression checks.",
    )
    parser.add_argument(
        "--frontend-url",
        default=DEFAULT_FRONTEND_URL,
        help=f"Frontend base URL (default: {DEFAULT_FRONTEND_URL})",
    )
    parser.add_argument(
        "--trend-output",
        default=os.environ.get("CHAT_REGRESSION_TREND_OUTPUT"),
        help="Optional JSONL path for long-chat regression trend records.",
    )
    parser.add_argument(
        "--screenshot-dir",
        default=os.environ.get("CHAT_REGRESSION_SCREENSHOT_DIR"),
        help="Optional directory for right-panel visual regression screenshots.",
    )
    return parser.parse_args()


def _wait_for_chat_input(page, *, timeout: float = 30000):
    selectors = [
        'textarea[name="message"]',
        'textarea[data-slot="textarea"]',
        "form textarea",
        "textarea[placeholder]",
    ]
    per_selector_timeout = max(int(timeout / max(len(selectors), 1)), 1000)
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(timeout=per_selector_timeout)
            return locator
        except PlaywrightTimeoutError:
            continue

    body_preview = " ".join(page.locator("body").inner_text(timeout=3000).split())[:400]
    raise RuntimeError(
        f"Chat input did not become visible at {page.url!r}; body={body_preview!r}",
    )


def _find_attachment_button(page):
    for pattern in ("Add attachments", "附件", "添加", "新增附件"):
        locator = page.get_by_role("button", name=pattern).first
        try:
            locator.wait_for(timeout=1500)
            return locator
        except PlaywrightTimeoutError:
            continue

    button = page.locator(
        "button[aria-label*='attachment' i], button[title*='attachment' i], button[aria-label*='附件'], button[title*='附件']",
    ).first
    button.wait_for(timeout=5000)
    return button


def _install_local_state(context) -> None:
    context.add_init_script(
        """
        (() => {
          document.cookie = "locale=zh-CN; path=/";
          localStorage.setItem("octoagent.local-settings", JSON.stringify({
            setup: {
              completed: true,
              workspace_path: "/home/sieve-pub/public-workspace/octoagent",
              default_model: "nemotron-3-super-free",
              sandbox_mode: "local"
            },
            context: { model_name: "nemotron-3-super-free", mode: "flash" },
            layout: { sidebar_collapsed: false },
            appearance: { preset: "default" },
            notification: { enabled: true },
            bootstrap: { onboarding_enabled: false }
          }));
        })();
        """,
    )


def _load_recent_thread_ids(frontend_url: str, limit: int = 3) -> list[str]:
    payload = json.dumps(
        {
            "limit": limit,
            "sortBy": "updated_at",
            "sortOrder": "desc",
            "select": ["thread_id", "updated_at", "values"],
        },
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{frontend_url}/api/langgraph/threads/search",
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to load recent threads: {exc}") from exc

    if not isinstance(data, list):
        return []
    thread_ids: list[str] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("thread_id"), str):
            thread_ids.append(item["thread_id"])
    return thread_ids


def _fixture_langgraph_url(frontend_url: str) -> str:
    env_url = os.environ.get("OCTO_LANGGRAPH_URL")
    if env_url:
        return env_url.rstrip("/")
    parsed = urllib.parse.urlsplit(frontend_url)
    host = parsed.hostname or "127.0.0.1"
    scheme = parsed.scheme or "http"
    return urllib.parse.urlunsplit((scheme, f"{host}:19884", "", "", "")).rstrip("/")


def _api_json(base_url: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API {path} failed with HTTP {exc.code}: {body}") from exc


def _create_fixture_thread(
    frontend_url: str,
    messages: list[dict],
    extra_values: dict | None = None,
) -> str:
    langgraph_url = _fixture_langgraph_url(frontend_url)
    thread = _api_json(
        langgraph_url,
        "/threads",
        {"metadata": {"graph_id": "lead_agent", "fixture": "chat-regression"}},
    )
    thread_id = thread["thread_id"]
    _api_json(
        langgraph_url,
        f"/threads/{thread_id}/state",
        {"values": {"messages": messages, **(extra_values or {})}, "as_node": "model"},
    )
    return thread_id


def _write_thread_output_file(thread_id: str, relative_path: str, content: str) -> None:
    output_root = Path(__file__).resolve().parents[2] / "workspace" / "default" / "threads" / thread_id / "outputs"
    target = output_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _write_trend_record(output: Path | str, result: ChatRegressionResult) -> None:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "long_scroll_message_count": result.long_scroll_message_count,
        "long_scroll_render_ms": result.long_scroll_render_ms,
        "long_scroll_stable": result.long_scroll_stable,
        "critical_browser_error_count": len(result.critical_browser_errors),
    }
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def _capture_right_panel_visuals(page, frontend_url: str, screenshot_dir: str | None) -> list[str]:
    if not screenshot_dir:
        return []

    thread_id = _create_fixture_thread(
        frontend_url,
        [
            {"id": "h-artifact-1", "type": "human", "content": "生成结果文档。"},
            {"id": "ai-artifact-1", "type": "ai", "content": "已生成右侧 Artifact 面板视觉回归文档。"},
        ],
        {"artifacts": ["/mnt/user-data/outputs/right-panel-report.md"]},
    )
    _write_thread_output_file(
        thread_id,
        "right-panel-report.md",
        "# Right Panel Report\n\n- Execution console remains separate.\n- Artifact preview and download controls are visible.\n",
    )

    output_dir = Path(screenshot_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    captures: list[str] = []
    for name, viewport in (
        ("right-panel-artifact-desktop.png", {"width": 1440, "height": 960}),
        ("right-panel-artifact-mobile.png", {"width": 390, "height": 844}),
    ):
        page.set_viewport_size(viewport)
        page.goto(f"{frontend_url}/workspace/chats/{thread_id}", wait_until="domcontentloaded")
        _wait_for_chat_input(page, timeout=15000)
        artifacts_tab = page.get_by_role("tab", name=re.compile(r"^(Artifacts|文件|工件|產物)$")).first
        artifacts_tab.wait_for(timeout=15000)
        artifacts_tab.click()
        page.get_by_text("right-panel-report.md", exact=False).first.wait_for(timeout=15000)
        page.get_by_text("right-panel-report.md", exact=False).first.click()
        page.get_by_text("Right Panel Report", exact=False).first.wait_for(timeout=15000)
        target = output_dir / name
        page.screenshot(path=str(target), full_page=True)
        captures.append(str(target))
    return captures


def _ordinary_tool_messages() -> list[dict]:
    return [
        {"id": "h-ordinary-1", "type": "human", "content": "列出工作目录。"},
        {
            "id": "ai-ordinary-1",
            "type": "ai",
            "content": "",
            "tool_calls": [
                {
                    "id": "tool-ordinary-1",
                    "name": "ls",
                    "args": {
                        "description": "list workspace",
                        "path": "/mnt/user-data/workspace",
                    },
                },
            ],
        },
        {
            "id": "tool-ordinary-1-result",
            "type": "tool",
            "name": "ls",
            "tool_call_id": "tool-ordinary-1",
            "content": "README.md\nfrontend\nbackend",
        },
        {"id": "ai-ordinary-2", "type": "ai", "content": "目录包含 README.md、frontend 和 backend。"},
    ]


def _web_tool_chain_messages() -> list[dict]:
    return [
        {"id": "h-web-1", "type": "human", "content": "搜索 OctoAgent 文档并打开相关页面。"},
        {
            "id": "ai-web-1",
            "type": "ai",
            "content": "",
            "tool_calls": [
                {
                    "id": "tool-web-search-1",
                    "name": "web_search",
                    "args": {"query": "OctoAgent documentation"},
                },
            ],
        },
        {
            "id": "tool-web-search-1-result",
            "type": "tool",
            "name": "web_search",
            "tool_call_id": "tool-web-search-1",
            "content": json.dumps(
                {
                    "results": [
                        {
                            "title": "OctoAgent Docs",
                            "url": "https://example.test/octoagent",
                            "snippet": "Open source multi-agent workspace.",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        },
        {
            "id": "ai-web-2",
            "type": "ai",
            "content": "",
            "tool_calls": [
                {
                    "id": "tool-web-fetch-1",
                    "name": "web_fetch",
                    "args": {"url": "https://example.test/octoagent"},
                },
                {
                    "id": "tool-read-webpage-1",
                    "name": "read_webpage",
                    "args": {"url": "https://example.test/octoagent/guide"},
                },
            ],
        },
        {
            "id": "tool-web-fetch-1-result",
            "type": "tool",
            "name": "web_fetch",
            "tool_call_id": "tool-web-fetch-1",
            "content": "# OctoAgent\n\nA multi-model multi-agent OS workspace.",
        },
        {
            "id": "tool-read-webpage-1-result",
            "type": "tool",
            "name": "read_webpage",
            "tool_call_id": "tool-read-webpage-1",
            "content": "Guide page loaded with setup and runtime details.",
        },
        {"id": "ai-web-3", "type": "ai", "content": "已完成搜索、抓取和网页读取链路。"},
        {"id": "h-web-2", "type": "human", "content": "继续总结重点。"},
        {"id": "ai-web-4", "type": "ai", "content": "重点：多模型、多 Agent、工具链和运行时状态一致。"},
    ]


def _multi_turn_messages() -> list[dict]:
    messages: list[dict] = []
    for index in range(1, 5):
        messages.append(
            {
                "id": f"h-multi-{index}",
                "type": "human",
                "content": f"第 {index} 轮：记录一句状态。",
            },
        )
        messages.append(
            {
                "id": f"ai-multi-{index}",
                "type": "ai",
                "content": f"已记录第 {index} 轮状态。",
            },
        )
    return messages


def _long_thread_messages(count: int = 520) -> list[dict]:
    messages: list[dict] = []
    for index in range(count):
        messages.append(
            {
                "id": f"long-{index}",
                "type": "human" if index % 2 == 0 else "ai",
                "content": f"长对话性能压测消息 {index}: OctoAgent scroll stability check.",
            },
        )
    return messages


def main() -> None:
    args = _parse_args()
    result = ChatRegressionResult()
    stale_thread_id = str(uuid.uuid4())

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**_browser_launch_options(playwright))
        context = browser.new_context(locale="zh-CN", viewport={"width": 1280, "height": 900})
        _install_local_state(context)
        page = context.new_page()

        def record_critical(text: str) -> None:
            if any(
                marker in text
                for marker in (
                    "Maximum update depth exceeded",
                    "Permission denied when creating directories",
                    "[ChatThreadError]",
                    "Unable to connect to LangGraph server",
                )
            ):
                result.critical_browser_errors.append(text[:1000])

        page.on("pageerror", lambda error: record_critical(str(error)))
        page.on(
            "console",
            lambda msg: record_critical(msg.text) if msg.type in {"error", "warning"} else None,
        )

        page.goto(f"{args.frontend_url}/workspace/chats/new", wait_until="domcontentloaded")
        _wait_for_chat_input(page)
        welcome = page.get_by_text("欢迎使用 🐙 OctoAgent", exact=False).first
        welcome.wait_for(timeout=30000)
        welcome_state = welcome.evaluate(
            """(el) => {
              const style = getComputedStyle(el);
              return {
                text: el.textContent || "",
                textAlign: style.textAlign,
                textIndent: style.textIndent,
                whiteSpace: style.whiteSpace
              };
            }""",
        )
        result.welcome_copy_normalized = "\n" not in welcome_state["text"] and welcome_state["textAlign"] == "left" and welcome_state["whiteSpace"] == "normal" and welcome_state["textIndent"] != "0px"
        if not result.welcome_copy_normalized:
            result.notes.append(f"welcome_state={welcome_state!r}")

        attachment = _find_attachment_button(page)
        attachment.hover()
        page.wait_for_timeout(1000)
        result.attachment_button_stable = not result.critical_browser_errors

        page.goto(
            f"{args.frontend_url}/workspace/chats/{stale_thread_id}",
            wait_until="domcontentloaded",
        )
        _wait_for_chat_input(page, timeout=12000)
        result.stale_thread_shell_restored = True

        page.goto(
            f"{args.frontend_url}/workspace/chats/new?continue_from={stale_thread_id}",
            wait_until="domcontentloaded",
        )
        _wait_for_chat_input(page, timeout=12000)
        result.continuation_shell_ready = True

        ordinary_thread_id = _create_fixture_thread(args.frontend_url, _ordinary_tool_messages())
        before_error_count = len(result.critical_browser_errors)
        page.goto(
            f"{args.frontend_url}/workspace/chats/{ordinary_thread_id}",
            wait_until="domcontentloaded",
        )
        _wait_for_chat_input(page, timeout=15000)
        page.wait_for_timeout(2000)
        result.ordinary_tool_history_stable = len(result.critical_browser_errors) == before_error_count

        web_tool_thread_id = _create_fixture_thread(args.frontend_url, _web_tool_chain_messages())
        before_error_count = len(result.critical_browser_errors)
        page.goto(
            f"{args.frontend_url}/workspace/chats/{web_tool_thread_id}",
            wait_until="domcontentloaded",
        )
        _wait_for_chat_input(page, timeout=15000)
        page.wait_for_timeout(2000)
        result.web_tool_chain_history_stable = len(result.critical_browser_errors) == before_error_count

        context_guard_thread_id = _create_fixture_thread(
            args.frontend_url,
            _ordinary_tool_messages(),
            {
                "runtime": {
                    "memory_guard_state": "ok",
                    "context_guard_state": "truncated",
                    "context_pressure": "medium",
                    "recommended_memory_action": "truncate_oversized_messages",
                }
            },
        )
        before_error_count = len(result.critical_browser_errors)
        page.goto(
            f"{args.frontend_url}/workspace/chats/{context_guard_thread_id}",
            wait_until="domcontentloaded",
        )
        _wait_for_chat_input(page, timeout=15000)
        page.get_by_text("上下文守护已缩短超大消息", exact=False).first.wait_for(timeout=15000)
        result.context_guard_notice_visible = len(result.critical_browser_errors) == before_error_count

        multi_turn_thread_id = _create_fixture_thread(args.frontend_url, _multi_turn_messages())
        before_error_count = len(result.critical_browser_errors)
        page.goto(
            f"{args.frontend_url}/workspace/chats/{multi_turn_thread_id}",
            wait_until="domcontentloaded",
        )
        _wait_for_chat_input(page, timeout=15000)
        page.wait_for_timeout(2000)
        result.multi_turn_history_stable = len(result.critical_browser_errors) == before_error_count

        before_error_count = len(result.critical_browser_errors)
        page.goto(
            f"{args.frontend_url}/workspace/chats/new?continue_from={multi_turn_thread_id}",
            wait_until="domcontentloaded",
        )
        _wait_for_chat_input(page, timeout=15000)
        page.wait_for_timeout(2000)
        result.continuation_history_stable = len(result.critical_browser_errors) == before_error_count

        long_thread_id = _create_fixture_thread(
            args.frontend_url,
            _long_thread_messages(result.long_scroll_message_count),
        )
        before_error_count = len(result.critical_browser_errors)
        page.goto(
            f"{args.frontend_url}/workspace/chats/{long_thread_id}",
            wait_until="domcontentloaded",
        )
        _wait_for_chat_input(page, timeout=20000)
        scroll_metrics = page.evaluate(
            """async () => {
              const scroller = document.querySelector('[data-chat-scroll-container="true"]');
              if (!scroller) return { ok: false, elapsed: -1 };
              const start = performance.now();
              for (let i = 0; i < 18; i += 1) {
                scroller.scrollTop = i % 2 === 0 ? scroller.scrollHeight : 0;
                await new Promise((resolve) => requestAnimationFrame(resolve));
              }
              return { ok: true, elapsed: Math.round(performance.now() - start) };
            }""",
        )
        result.long_scroll_render_ms = int(scroll_metrics.get("elapsed", -1))
        result.long_scroll_stable = bool(scroll_metrics.get("ok")) and result.long_scroll_render_ms >= 0 and result.long_scroll_render_ms < 5000 and len(result.critical_browser_errors) == before_error_count

        captures = _capture_right_panel_visuals(page, args.frontend_url, args.screenshot_dir)
        if captures:
            result.notes.append(f"right_panel_screenshots={captures}")

        recent_thread_ids = _load_recent_thread_ids(args.frontend_url, limit=3)
        if recent_thread_ids:
            for recent_thread_id in recent_thread_ids[:1]:
                before_error_count = len(result.critical_browser_errors)
                for suffix in ("", "?settings=models"):
                    page.goto(
                        f"{args.frontend_url}/workspace/chats/{recent_thread_id}{suffix}",
                        wait_until="domcontentloaded",
                    )
                    _wait_for_chat_input(page, timeout=15000)
                    page.wait_for_timeout(3000)
                result.existing_thread_route_stable = len(result.critical_browser_errors) == before_error_count
        else:
            result.existing_thread_route_stable = True
            result.notes.append("existing_thread_route_skipped:no_threads")

        browser.close()

    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    if args.trend_output:
        _write_trend_record(args.trend_output, result)
    if (
        not result.welcome_copy_normalized
        or not result.attachment_button_stable
        or not result.stale_thread_shell_restored
        or not result.continuation_shell_ready
        or not result.existing_thread_route_stable
        or not result.ordinary_tool_history_stable
        or not result.web_tool_chain_history_stable
        or not result.context_guard_notice_visible
        or not result.multi_turn_history_stable
        or not result.continuation_history_stable
        or not result.long_scroll_stable
        or result.critical_browser_errors
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
