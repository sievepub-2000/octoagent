"""Run a lightweight real-browser smoke test against the local OctoAgent UI."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import uuid
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

DEFAULT_FRONTEND_URL = "http://127.0.0.1:19880"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:19880"


@dataclass
class SmokeResult:
    backend_ok: bool = False
    frontend_ok: bool = False
    embedded_model_name: str | None = None
    models_api_count: int = 0
    embedded_backup_present: bool = False
    bootstrap_installed: bool = False
    chat_input_ready: bool = False
    chat_message_sent: bool = False
    multi_turn_message_sent: bool = False
    continuation_route_opened: bool = False
    workflow_task_created: bool = False
    task_workspace_cleaned: bool = False
    settings_opened: bool = False
    bootstrap_section_opened: bool = False
    guide_generated: bool = False
    notes: list[str] = field(default_factory=list)
    critical_browser_errors: list[str] = field(default_factory=list)


def _note(message: str) -> None:
    print(f"[smoke] {message}", file=sys.stderr, flush=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run browser/API smoke checks for local OctoAgent UI.",
    )
    parser.add_argument(
        "--frontend-url",
        default=DEFAULT_FRONTEND_URL,
        help=f"Frontend base URL (default: {DEFAULT_FRONTEND_URL})",
    )
    parser.add_argument(
        "--gateway-url",
        default=DEFAULT_GATEWAY_URL,
        help=f"Gateway base URL (default: {DEFAULT_GATEWAY_URL})",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Open /workspace/chats/new?mock=true instead of real route.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="HTTP/API timeout in seconds (default: 30).",
    )
    return parser.parse_args()


def _click_first_visible(page, selectors: list[tuple[str, str]], *, timeout: float = 3000) -> bool:
    for kind, value in selectors:
        locator = (
            page.get_by_role("button", name=value)
            if kind == "role_button"
            else page.get_by_role("menuitem", name=value)
            if kind == "role_menuitem"
            else page.locator(value)
        )
        try:
            locator.first.wait_for(timeout=timeout)
            locator.first.click()
            return True
        except PlaywrightTimeoutError:
            continue
    return False


def _wait_for_chat_input(
    page,
    *,
    timeout: float = 30000,
    page_errors: list[str] | None = None,
    console_errors: list[str] | None = None,
):
    selectors = [
        'textarea[name="message"]',
        'textarea[data-slot="textarea"]',
        "form textarea",
        'textarea[placeholder]',
    ]
    per_selector_timeout = max(int(timeout / max(len(selectors), 1)), 1000)
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(timeout=per_selector_timeout)
            return locator
        except PlaywrightTimeoutError:
            continue

    textarea_count = page.locator("textarea").count()
    body_text = page.locator("body").inner_text(timeout=3000)
    body_preview = " ".join(body_text.split())[:400]
    raise RuntimeError(
        "Chat input did not become visible. "
        f"url={page.url!r} title={page.title()!r} "
        f"textarea_count={textarea_count} body_preview={body_preview!r} "
        f"page_errors={page_errors or []!r} console_errors={console_errors or []!r}"
    )


def _wait_for_any_text(page, candidates: list[str], *, timeout: float = 10000) -> str:
    per_candidate_timeout = max(int(timeout / max(len(candidates), 1)), 1000)
    for text in candidates:
        try:
            page.get_by_text(text, exact=False).first.wait_for(timeout=per_candidate_timeout)
            return text
        except PlaywrightTimeoutError:
            continue
    raise PlaywrightTimeoutError(f"None of the expected texts became visible: {candidates!r}")


def _resolve_thread_id_from_search(gateway_url: str, smoke_message: str, timeout_seconds: float) -> str | None:
    with httpx.Client(timeout=timeout_seconds, trust_env=False) as client:
        response = client.post(
            f"{gateway_url}/api/langgraph/threads/search",
            json={
                "limit": 10,
                "sortBy": "updated_at",
                "sortOrder": "desc",
                "select": ["thread_id", "updated_at", "values"],
            },
        )
        response.raise_for_status()
        threads = response.json()

    for thread in threads:
        messages = (thread.get("values") or {}).get("messages") or []
        if not messages:
            continue
        first_message = messages[0]
        content = first_message.get("content")
        if isinstance(content, str) and smoke_message in content:
            return thread.get("thread_id")

    if threads:
        return threads[0].get("thread_id")

    return None


def _goto_with_recovery(
    page,
    url: str,
    *,
    wait_until: str,
    timeout: float = 30000,
) -> None:
    try:
        page.goto(url, wait_until=wait_until, timeout=timeout)
        return
    except PlaywrightTimeoutError:
        target = urlsplit(url)
        current = urlsplit(page.url)
        if current.path == target.path and current.query == target.query:
            _note(
                "page.goto timed out after route change, continuing because the browser is already on the target URL",
            )
            return

    page.goto(url, wait_until="commit", timeout=max(int(timeout / 3), 5000))


def _complete_setup_wizard_if_present(page) -> None:
    wizard_markers = [
        "Model Configuration",
        "Create the first model",
        "Start Using OctoAgent",
        "开始使用 OctoAgent",
    ]
    wizard_visible = False
    for marker in wizard_markers:
        try:
            page.get_by_text(marker, exact=False).first.wait_for(timeout=1200)
            wizard_visible = True
            break
        except PlaywrightTimeoutError:
            continue
    if not wizard_visible:
        return

    finish_labels = (
        "Finish setup",
        "Start Using OctoAgent",
        "开始使用 OctoAgent",
        "開始使用 OctoAgent",
        "OctoAgent を使い始める",
        "OctoAgent 사용 시작",
    )

    # New single-step wizard: choose the default model if needed, then finish.
    try:
        trigger = page.locator('[role="combobox"]').first
        if trigger.count() > 0:
            trigger.click(timeout=3000)
            page.locator('[role="option"]').first.click(timeout=3000)
    except Exception:
        pass

    for label in finish_labels:
        try:
            button = page.get_by_role("button", name=label)
            button.wait_for(timeout=3000)
            if button.is_enabled():
                button.click(timeout=4000)
                return
        except Exception:
            continue

    # Legacy multi-step wizard fallback.
    for label in ("Next", "下一步", "次へ", "다음"):
        try:
            page.get_by_role("button", name=label).click(timeout=3000)
            break
        except Exception:
            continue

    try:
        trigger = page.locator('[role="combobox"]').first
        if trigger.count() > 0:
            trigger.click(timeout=3000)
            page.locator('[role="option"]').first.click(timeout=3000)
    except Exception:
        pass

    for label in ("Next", "下一步", "次へ", "다음"):
        try:
            page.get_by_role("button", name=label).click(timeout=3000)
            break
        except Exception:
            continue

    for label in finish_labels:
        try:
            page.get_by_role("button", name=label).click(timeout=4000)
            return
        except Exception:
            continue

_CRITICAL_BROWSER_ERROR_RE = re.compile(
    r"FileNotFoundError|Agent directory not found|An internal error occurred|"
    r"Unknown scheme for proxy|Unhandled Runtime Error|Permission denied",
    re.IGNORECASE,
)


def _critical_browser_errors(page_errors: list[str], console_errors: list[str]) -> list[str]:
    return [
        message
        for message in [*page_errors, *console_errors]
        if _CRITICAL_BROWSER_ERROR_RE.search(message)
    ]


def main() -> int:
    args = _parse_args()
    result = SmokeResult()
    route_transition_timeout_ms = max(int(args.timeout_seconds * 1500), 15000)

    with httpx.Client(timeout=args.timeout_seconds, trust_env=False) as client:
        _note("checking bootstrap status")
        status = client.get(f"{args.gateway_url}/api/bootstrap/status")
        status.raise_for_status()
        bootstrap = status.json()
        result.backend_ok = True
        result.bootstrap_installed = bool(bootstrap.get("installed"))
        result.embedded_model_name = bootstrap.get("recommended_model")

        _note("checking models api")
        models = client.get(f"{args.gateway_url}/api/models")
        models.raise_for_status()
        models_payload = models.json().get("models", [])
        result.models_api_count = len(models_payload)
        result.embedded_backup_present = any(
            bool(model.get("is_embedded_backup")) for model in models_payload
        )

        _note("creating task workspace")
        task_workspace = client.post(
            f"{args.gateway_url}/api/task-workspaces",
            json={"name": f"Smoke Task {uuid.uuid4().hex[:8]}", "mode": "single"},
        )
        task_workspace.raise_for_status()
        task_workspace_id = task_workspace.json()["task_id"]

    with sync_playwright() as playwright:
        _note("launching browser")
        browser_executable = (
            os.environ.get("OCTOPUSAGENT_BROWSER_PATH")
            or playwright.chromium.executable_path
            or shutil.which("chromium-browser")
            or shutil.which("chromium")
            or shutil.which("google-chrome")
        )
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=browser_executable,
        )
        page = browser.new_page()
        page_errors: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text)
            if msg.type == "error" and len(console_errors) < 10
            else None,
        )
        chat_url = (
            f"{args.frontend_url}/workspace/chats/new?mock=true"
            if args.mock
            else f"{args.frontend_url}/workspace/chats/new"
        )
        _note(f"opening chat url: {chat_url}")
        # The chat shell can keep background requests alive, so relying on
        # networkidle causes false negatives even when the page is interactive.
        page.goto(chat_url, wait_until="domcontentloaded")
        _complete_setup_wizard_if_present(page)
        title = page.title()
        result.frontend_ok = ("OctoAgent" in title) or ("OctoAgent" in title)
        _note("waiting for chat input")
        chat_box = _wait_for_chat_input(
            page,
            page_errors=page_errors,
            console_errors=console_errors,
        )
        result.chat_input_ready = True

        smoke_message = "Smoke test message for embedded fallback validation."
        _note("sending smoke message")
        chat_box.fill(smoke_message)
        chat_box.press("Enter")
        try:
            _note("waiting for sent message to appear")
            page.get_by_text(smoke_message, exact=False).wait_for(timeout=10000)
        except PlaywrightTimeoutError:
            if "new" in page.url:
                _click_first_visible(
                    page,
                    [("role_button", "Submit"), ("role_button", "发送"), ("role_button", "送信")],
                    timeout=3000,
                )
                page.get_by_text(smoke_message, exact=False).wait_for(timeout=10000)
        result.chat_message_sent = True

        if "/workspace/chats/new" in page.url:
            _note("waiting for real thread route after optimistic message render")
            try:
                page.wait_for_url(
                    re.compile(r".*/workspace/chats/(?!new(?:\?|$))[^/?#]+(?:\?.*)?$"),
                    timeout=route_transition_timeout_ms,
                )
            except PlaywrightTimeoutError as error:
                recovered_thread_id = _resolve_thread_id_from_search(
                    args.gateway_url,
                    smoke_message,
                    args.timeout_seconds,
                )
                if not recovered_thread_id:
                    raise RuntimeError(
                        "Thread URL did not switch from /new after submitting the first message. "
                        f"url={page.url!r} title={page.title()!r} "
                        f"page_errors={page_errors or []!r} console_errors={console_errors or []!r}"
                    ) from error

                result.notes.append("thread_route_fallback_used")
                current_thread_id = recovered_thread_id
            else:
                current_url = page.url
                current_thread_id = current_url.rstrip("/").split("/")[-1].split("?")[0]
        else:
            current_url = page.url
            current_thread_id = current_url.rstrip("/").split("/")[-1].split("?")[0]
        if current_thread_id == "new":
            raise RuntimeError(
                "Smoke script resolved thread id 'new' after submission, which means the conversation route "
                "never switched to a real thread. "
                f"url={current_url!r} page_errors={page_errors or []!r} console_errors={console_errors or []!r}"
            )

        follow_up_message = "Follow-up smoke turn for conversation regression."
        _note("opening resolved thread route before follow-up smoke message")
        _goto_with_recovery(
            page,
            f"{args.frontend_url}/workspace/chats/{current_thread_id}",
            wait_until="domcontentloaded",
        )
        _note("sending follow-up smoke message on existing thread")
        follow_up_box = _wait_for_chat_input(
            page,
            page_errors=page_errors,
            console_errors=console_errors,
        )
        follow_up_box.fill(follow_up_message)
        follow_up_box.press("Enter")
        try:
            page.get_by_text(follow_up_message, exact=False).wait_for(timeout=30000)
            result.multi_turn_message_sent = True
        except PlaywrightTimeoutError:
            submitted = _click_first_visible(
                page,
                [
                    ("role_button", "Submit"),
                    ("role_button", "发送"),
                    ("role_button", "送信"),
                    ("locator", 'form button[type="submit"]'),
                    ("locator", 'button[type="submit"]'),
                ],
                timeout=3000,
            )
            if submitted:
                try:
                    page.get_by_text(follow_up_message, exact=False).wait_for(timeout=30000)
                    result.multi_turn_message_sent = True
                except PlaywrightTimeoutError:
                    pass
            else:
                result.notes.append("follow_up_submit_button_not_found")

        if not result.multi_turn_message_sent:
            try:
                with httpx.Client(timeout=args.timeout_seconds, trust_env=False) as client:
                    response = client.get(f"{args.gateway_url}/api/langgraph/threads/{current_thread_id}/state")
                    response.raise_for_status()
                    messages = (response.json().get("values") or {}).get("messages") or []
                for message in messages:
                    content = message.get("content")
                    if isinstance(content, list):
                        content_text = " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
                    else:
                        content_text = str(content or "")
                    if follow_up_message in content_text:
                        result.multi_turn_message_sent = True
                        result.notes.append("follow_up_confirmed_from_thread_state")
                        break
            except Exception as exc:
                result.notes.append(f"follow_up_state_check_failed:{exc}")
        if not result.multi_turn_message_sent:
            raise RuntimeError(
                "Follow-up smoke message was not observed after submit. "
                f"url={page.url!r} page_errors={page_errors or []!r} console_errors={console_errors or []!r}"
            )

        _note(f"opening continuation route for thread {current_thread_id}")
        _goto_with_recovery(
            page,
            f"{args.frontend_url}/workspace/chats/new?continue_from={current_thread_id}",
            wait_until="domcontentloaded",
        )
        _note("waiting for continuation input")
        _wait_for_chat_input(
            page,
            page_errors=page_errors,
            console_errors=console_errors,
        )
        result.continuation_route_opened = "continue_from=" in page.url

        _note("opening workspace settings")
        settings_dialog_visible = False
        if not _click_first_visible(
            page,
            [
                ("locator", "#workspace-system-settings-trigger"),
                ("locator", '[data-sidebar="footer"] [data-sidebar="menu-button"]'),
                ("role_button", "Settings and more"),
                ("role_button", "设置和更多"),
                ("locator", '[data-sidebar="menu-button"]'),
            ],
        ):
            result.notes.append("settings_menu_trigger_not_clicked")
        else:
            try:
                page.wait_for_url(re.compile(r".*[?&]settings=[^&#]+.*"), timeout=3000)
                settings_dialog_visible = True
            except PlaywrightTimeoutError:
                settings_dialog_visible = False

        if not settings_dialog_visible and _click_first_visible(
            page,
            [
                ("role_menuitem", "Settings"),
                ("role_menuitem", "设置"),
                ("role_menuitem", "System Settings"),
                ("role_menuitem", "系统设置"),
                ("locator", '[role="menuitem"]:has-text("Settings")'),
                ("locator", '[role="menuitem"]:has-text("设置")'),
            ],
            timeout=3000,
        ):
            try:
                page.wait_for_url(re.compile(r".*[?&]settings=[^&#]+.*"), timeout=3000)
                settings_dialog_visible = True
            except PlaywrightTimeoutError:
                settings_dialog_visible = False

        if not settings_dialog_visible:
            result.notes.append("settings_menu_fallback_to_query")
            deep_link_url = f"{args.frontend_url}/workspace/chats/{current_thread_id}?settings=bootstrap"
            _goto_with_recovery(page, deep_link_url, wait_until="domcontentloaded")
            try:
                _wait_for_any_text(
                    page,
                    ["Settings", "设置", "系统设置", "Embedded Bootstrap Model", "内嵌引导模型"],
                    timeout=10000,
                )
                settings_dialog_visible = True
            except PlaywrightTimeoutError as error:
                raise RuntimeError(
                    "Could not open the Settings dialog from the workspace menu or the deep-link fallback. "
                    f"url={page.url!r} page_errors={page_errors or []!r} console_errors={console_errors or []!r}"
                ) from error

        if not settings_dialog_visible:
            raise RuntimeError("Could not open the Settings dialog.")

        for heading_name in ("Settings", "设置", "系统设置"):
            try:
                page.get_by_role("heading", name=heading_name).wait_for(timeout=3000)
                break
            except PlaywrightTimeoutError:
                continue
        else:
            raise RuntimeError("Settings dialog opened without a recognizable heading.")

        if current_thread_id == "new":
            raise RuntimeError(
                "Smoke script resolved thread id 'new' after submission, which means the conversation route "
                "never switched to a real thread. "
                f"url={current_url!r} page_errors={page_errors or []!r} console_errors={console_errors or []!r}"
            )
        result.settings_opened = True

        _note("opening bootstrap settings section")
        bootstrap_settings_url = (
            f"{args.frontend_url}/workspace/chats/{current_thread_id}?settings=bootstrap"
        )
        if page.url != bootstrap_settings_url:
            _goto_with_recovery(
                page,
                bootstrap_settings_url,
                wait_until="domcontentloaded",
            )

        _note("waiting for bootstrap settings content")
        _wait_for_any_text(
            page,
            [
                "Embedded Bootstrap Model",
                "内嵌引导模型",
                "Recommended embedded runtime",
                "推荐的内嵌运行时",
                "Model status",
                "模型状态",
            ],
            timeout=10000,
        )
        result.bootstrap_section_opened = True
        try:
            _wait_for_any_text(
                page,
                [
                    "Recommended embedded runtime",
                    "推荐的内嵌运行时",
                    "Model status",
                    "模型状态",
                ],
                timeout=10000,
            )
        except PlaywrightTimeoutError:
            result.notes.append("bootstrap_hint_text_not_found")
        try:
            page.get_by_text("Gemma 3 270M IT GGUF Q4_K_M", exact=False).first.wait_for(
                timeout=10000
            )
        except PlaywrightTimeoutError:
            result.notes.append("bootstrap_model_label_not_found")

        guide_button = page.get_by_role("button", name="Generate guide")
        try:
            guide_button.wait_for(timeout=1500)
        except PlaywrightTimeoutError:
            result.guide_generated = True
        else:
            try:
                _note("generating bootstrap guide")
                guide_button.click()
                page.get_by_text("Install the embedded model", exact=False).wait_for(
                    state="detached",
                    timeout=20000,
                )
                result.guide_generated = True
            except PlaywrightTimeoutError:
                result.notes.append("bootstrap_guide_generation_not_observed")

        page.keyboard.press("Escape")
        _note("opening task workspace page")
        page.goto(
            f"{args.frontend_url}/workspace/tasks/{task_workspace_id}",
            wait_until="domcontentloaded",
        )
        page.wait_for_url(
            re.compile(
                rf".*/workspace/(?:tasks|workflows)/{re.escape(task_workspace_id)}(?:\?.*)?$"
            ),
            timeout=10000,
        )
        if (
            f"/workspace/tasks/{task_workspace_id}" not in page.url
            and f"/workspace/workflows/{task_workspace_id}" not in page.url
        ):
            raise RuntimeError(
                f"Task workspace route did not resolve to a task detail page: {page.url}"
            )
        result.workflow_task_created = True

        result.critical_browser_errors = _critical_browser_errors(page_errors, console_errors)
        if result.critical_browser_errors:
            raise RuntimeError(
                "Critical browser errors were observed during WebUI smoke: "
                f"{result.critical_browser_errors!r}"
            )

        browser.close()

    with httpx.Client(timeout=args.timeout_seconds, trust_env=False) as client:
        try:
            cleanup = client.delete(f"{args.gateway_url}/api/task-workspaces/{task_workspace_id}")
            result.task_workspace_cleaned = cleanup.status_code in {200, 204, 404}
            if not result.task_workspace_cleaned:
                result.notes.append(f"task_workspace_cleanup_status={cleanup.status_code}")
        except Exception as exc:
            result.notes.append(f"task_workspace_cleanup_failed={exc}")

    required_flags = {
        "backend_ok": result.backend_ok,
        "frontend_ok": result.frontend_ok,
        "chat_input_ready": result.chat_input_ready,
        "chat_message_sent": result.chat_message_sent,
        "multi_turn_message_sent": result.multi_turn_message_sent,
        "continuation_route_opened": result.continuation_route_opened,
        "workflow_task_created": result.workflow_task_created,
        "task_workspace_cleaned": result.task_workspace_cleaned,
        "settings_opened": result.settings_opened,
        "bootstrap_section_opened": result.bootstrap_section_opened,
        "guide_generated": result.guide_generated,
    }
    missing = [name for name, ok in required_flags.items() if not ok]
    if missing:
        result.notes.append(f"required_flags_failed={','.join(missing)}")

    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if not missing and not result.critical_browser_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
