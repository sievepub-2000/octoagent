"""Execution helpers for browser runtime sessions."""

from __future__ import annotations

import os
import shutil
import threading
from collections.abc import Callable
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

import httpx

from .contracts import (
    BrowserActionExecutionRequest,
    BrowserActionExecutionResult,
    BrowserExecutionSession,
    BrowserSessionEvent,
    BrowserSessionRecoveryRequest,
    BrowserSessionUpdateRequest,
)
from .policy import BrowserSessionPolicy

BrowserFetch = dict[str, str | int | list[str] | None]


def _run_browser_call(call: Callable[[], Any]) -> Any:
    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def target() -> None:
        try:
            result["value"] = call()
        except BaseException as exc:
            error["value"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error["value"]
    return result["value"]


def extract_title(html: str) -> str | None:
    lowered = html.lower()
    start = lowered.find("<title")
    if start == -1:
        return None
    start = lowered.find(">", start)
    if start == -1:
        return None
    end = lowered.find("</title>", start)
    if end == -1:
        return None
    title = unescape(html[start + 1 : end]).strip()
    return title or None


class _PageStructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets: list[str] = []
        self.inputs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a":
            href = attributes.get("href")
            if href:
                self.targets.append(href)
        elif tag == "input":
            name = attributes.get("name")
            if name:
                self.inputs.append(name)


def extract_page_structure(html: str, base_url: str) -> tuple[list[str], list[str]]:
    parser = _PageStructureParser()
    parser.feed(html)
    resolved_targets = [urljoin(base_url, target) for target in parser.targets]
    return list(dict.fromkeys(resolved_targets)), list(dict.fromkeys(parser.inputs))


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _configured_browser():
    try:
        from src.runtime.config.integrations_config import get_integrations_config

        return get_integrations_config().browser
    except Exception:
        return None


def _resolve_browser_executable(config) -> str | None:
    configured = os.environ.get("OCTO_BROWSER_EXECUTABLE_PATH") or getattr(config, "executable_path", None)
    if configured and Path(configured).exists():
        return str(Path(configured))
    if not _truthy(os.environ.get("OCTO_BROWSER_AUTODETECT_EXECUTABLE")):
        return None
    for candidate in ("chromium", "google-chrome", "chromium-browser"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    for candidate in ("/snap/bin/chromium", "/usr/bin/chromium", "/usr/bin/google-chrome"):
        if Path(candidate).exists():
            return candidate
    return None


def _artifact_root(config) -> Path:
    configured = getattr(config, "artifacts_dir", None) if config is not None else None
    if configured:
        root = Path(configured)
        if not root.is_absolute():
            root = Path.cwd().parent / configured if Path.cwd().name == "backend" else Path.cwd() / configured
        root.mkdir(parents=True, exist_ok=True)
        return root
    from src.runtime.config.paths import get_paths

    root = get_paths().browser_runtime_dir / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root


class EmbeddedHeadlessProvider:
    def __init__(self):
        self.config = _configured_browser()

    @property
    def enabled(self) -> bool:
        config = self.config
        if config is None:
            return False
        return bool(getattr(config, "enabled", False) and getattr(config, "embedded_headless", True))

    @property
    def engine(self) -> str:
        return str(getattr(self.config, "engine", "playwright") or "playwright")

    def _sync_playwright(self):
        engine = self.engine
        if engine == "patchright":
            from patchright.sync_api import sync_playwright

            return sync_playwright
        if engine == "camoufox":
            try:
                from camoufox.sync_api import sync_playwright

                return sync_playwright
            except Exception:
                from playwright.sync_api import sync_playwright

                return sync_playwright
        from playwright.sync_api import sync_playwright

        return sync_playwright

    def _launch_kwargs(self) -> dict[str, Any]:
        config = self.config
        kwargs: dict[str, Any] = {
            "headless": bool(getattr(config, "headless", True)),
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        executable_path = _resolve_browser_executable(config)
        if executable_path:
            kwargs["executable_path"] = executable_path
        return kwargs

    def fetch_page(self, target: str) -> BrowserFetch:
        sync_playwright = self._sync_playwright()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**self._launch_kwargs())
            try:
                page = browser.new_page(viewport={"width": 1365, "height": 900})
                page.goto(target, wait_until="domcontentloaded", timeout=15000)
                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass
                content = page.content()
                targets = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href).filter(Boolean)")
                inputs = page.eval_on_selector_all(
                    "input[name], textarea[name], select[name]",
                    "els => els.map(e => e.getAttribute('name')).filter(Boolean)",
                )
                return {
                    "final_url": page.url,
                    "title": page.title(),
                    "status_code": 200,
                    "content_length": len(content),
                    "available_targets": list(dict.fromkeys(targets)),
                    "available_inputs": list(dict.fromkeys(inputs)),
                }
            finally:
                browser.close()

    def screenshot(self, session: BrowserExecutionSession, target: str) -> str:
        sync_playwright = self._sync_playwright()
        artifact_dir = _artifact_root(self.config) / session.session_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{len(session.executed_action_ids) + 1:03d}-screenshot.png"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**self._launch_kwargs())
            try:
                page = browser.new_page(viewport={"width": 1365, "height": 900})
                page.goto(target, wait_until="domcontentloaded", timeout=15000)
                page.screenshot(path=str(artifact_path), full_page=True)
            finally:
                browser.close()
        return str(artifact_path)

    def evaluate(self, target: str, script: str) -> str:
        sync_playwright = self._sync_playwright()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**self._launch_kwargs())
            try:
                page = browser.new_page(viewport={"width": 1365, "height": 900})
                page.goto(target, wait_until="domcontentloaded", timeout=15000)
                result = page.evaluate(script)
                return str(result)
            finally:
                browser.close()


class BrowserSessionExecutionEngine:
    """Apply session transitions and browser actions."""

    def __init__(self, *, policy: BrowserSessionPolicy):
        self._policy = policy

    def fetch_page(self, target: str) -> BrowserFetch:
        provider = EmbeddedHeadlessProvider()
        if provider.enabled and provider.engine not in {"none", "remote_cdp", "cloakbrowser"}:
            try:
                return provider.fetch_page(target)
            except Exception:
                if _truthy(os.environ.get("OCTO_BROWSER_REQUIRE_HEADLESS")):
                    raise
        response = httpx.get(target, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
        text = response.text
        title = extract_title(text)
        final_url = str(response.url)
        targets, inputs = extract_page_structure(text, final_url)
        return {
            "final_url": final_url,
            "title": title,
            "status_code": response.status_code,
            "content_length": len(text),
            "available_targets": targets,
            "available_inputs": inputs,
        }

    def sync_fetch_state(
        self,
        session: BrowserExecutionSession,
        fetch: BrowserFetch,
        *,
        snapshot: bool = False,
    ) -> None:
        session.current_url = str(fetch["final_url"] or session.current_url or session.target)
        session.page_title = str(fetch["title"] or "") or session.page_title
        session.last_fetch_status_code = int(fetch["status_code"]) if fetch["status_code"] is not None else None
        session.available_targets = list(fetch.get("available_targets") or [])
        session.available_inputs = list(fetch.get("available_inputs") or [])
        if snapshot:
            session.latest_snapshot_summary = (
                f"Snapshot for {session.current_url} "
                f"(status={session.last_fetch_status_code}, title={session.page_title or 'untitled'}, "
                f"bytes={fetch['content_length']}, links={len(session.available_targets)}, "
                f"inputs={len(session.available_inputs)})."
            )

    def append_event(
        self,
        session: BrowserExecutionSession,
        *,
        kind: Literal["created", "started", "completed", "failed", "note"],
        detail: str,
        created_at: str,
    ) -> None:
        session.events.append(
            BrowserSessionEvent(
                event_id=f"browser-event-{session.session_id}-{len(session.events) + 1}",
                session_id=session.session_id,
                kind=kind,
                detail=detail,
                created_at=created_at,
            )
        )

    def update_session(
        self,
        session: BrowserExecutionSession,
        request: BrowserSessionUpdateRequest,
        *,
        updated_at: str,
    ) -> BrowserExecutionSession:
        session.status = request.status
        session.updated_at = updated_at
        self.append_event(
            session,
            kind="started" if request.status == "running" else request.status,
            detail=request.detail or f"Browser session moved to '{request.status}'.",
            created_at=updated_at,
        )
        self._policy.refresh_pending_state(session)
        return session

    def recover_session(
        self,
        session: BrowserExecutionSession,
        request: BrowserSessionRecoveryRequest,
        *,
        recovered_at: str,
    ) -> BrowserExecutionSession:
        self._policy.refresh_pending_state(session)
        if not session.recovery_available:
            return session
        session.status = "planned"
        session.updated_at = recovered_at
        session.last_failure_detail = None
        self.append_event(
            session,
            kind="note",
            detail=request.note or "Browser session recovered for retry.",
            created_at=recovered_at,
        )
        self._policy.refresh_pending_state(session)
        return session

    def execute_next_action(
        self,
        session: BrowserExecutionSession,
        request: BrowserActionExecutionRequest,
        *,
        executed_at: str,
        fetch_page,
    ) -> BrowserActionExecutionResult:
        next_action = next(
            (action for action in session.planned_actions if action.action_id not in session.executed_action_ids),
            None,
        )
        if next_action is None:
            session.status = "completed"
            session.updated_at = executed_at
            self.append_event(
                session,
                kind="completed",
                detail="No remaining browser actions to execute.",
                created_at=executed_at,
            )
            return BrowserActionExecutionResult(
                session_id=session.session_id,
                action_id="none",
                status="completed",
                detail="No remaining browser actions to execute.",
                remaining_actions=0,
                current_url=session.current_url,
                page_title=session.page_title,
                snapshot_summary=session.latest_snapshot_summary,
                available_target_count=len(session.available_targets),
                available_input_count=len(session.available_inputs),
                recovery_available=False,
            )

        session.status = "running"
        session.updated_at = executed_at
        detail = request.note or f"Executed browser action '{next_action.action_id}' ({next_action.kind})."
        if not self._policy.is_allowed_target(session, next_action.target or session.current_url or session.target):
            detail = f"Blocked browser action '{next_action.action_id}' because the target is outside the allowed domains."
            return self._fail_action(session, next_action.action_id, detail, executed_at)
        try:
            session.executed_action_ids.append(next_action.action_id)
            remaining_actions = len(session.planned_actions) - len(session.executed_action_ids)
            artifact_path = None
            if next_action.kind == "open":
                fetch = fetch_page(next_action.target or session.target)
                self.sync_fetch_state(session, fetch)
                detail = f"Opened {session.current_url} with headless browser runtime (status={session.last_fetch_status_code}, title={session.page_title or 'untitled'})."
            elif next_action.kind == "snapshot":
                fetch = fetch_page(session.current_url or next_action.target or session.target)
                self.sync_fetch_state(session, fetch, snapshot=True)
                detail = session.latest_snapshot_summary or "Snapshot captured."
            elif next_action.kind == "screenshot":
                provider = EmbeddedHeadlessProvider()
                if not provider.enabled or provider.engine in {"none", "remote_cdp", "cloakbrowser"}:
                    raise ValueError("embedded headless provider is not enabled for screenshot")
                artifact_path = _run_browser_call(lambda: provider.screenshot(session, session.current_url or next_action.target or session.target))
                session.latest_artifact_path = artifact_path
                detail = f"Screenshot captured to {artifact_path}."
            elif next_action.kind == "eval":
                provider = EmbeddedHeadlessProvider()
                if not provider.enabled or provider.engine in {"none", "remote_cdp", "cloakbrowser"}:
                    raise ValueError("embedded headless provider is not enabled for eval")
                script = next_action.value or next_action.target or "document.title"
                result = _run_browser_call(lambda: provider.evaluate(session.current_url or session.target, script))
                detail = f"Evaluated browser script result: {result[:500]}"
            elif next_action.kind == "click":
                click_target = next_action.target or session.current_url or session.target
                resolved_target = urljoin(session.current_url or session.target, click_target)
                if not self._policy.is_allowed_target(session, resolved_target):
                    raise ValueError("resolved click target is outside the allowed domains")
                if session.available_targets and resolved_target not in session.available_targets:
                    raise ValueError("resolved click target is not present in the current page targets")
                fetch = fetch_page(resolved_target)
                self.sync_fetch_state(session, fetch)
                detail = f"Clicked to {session.current_url} (status={session.last_fetch_status_code}, title={session.page_title or 'untitled'})."
            elif next_action.kind == "fill":
                field_name = (next_action.target or "").strip()
                if not field_name:
                    raise ValueError("fill action requires a target field name")
                if session.available_inputs and field_name not in session.available_inputs:
                    raise ValueError("fill target is not present in the current page inputs")
                session.form_state[field_name] = next_action.value or ""
                detail = f"Filled field '{field_name}' with a staged value in the current browser session."
            elif next_action.kind == "wait":
                detail = f"Waited for '{next_action.target or next_action.value or 'next browser state'}'."

            result_status = "completed" if remaining_actions == 0 else "simulated"
            session.last_failure_detail = None
            session.last_action_id = next_action.action_id
            session.last_action_detail = detail
            session.last_action_status = result_status
            self._policy.refresh_pending_state(session)
            self.append_event(
                session,
                kind="started" if remaining_actions > 0 else "completed",
                detail=detail,
                created_at=executed_at,
            )
            if remaining_actions == 0:
                session.status = "completed"
            return BrowserActionExecutionResult(
                session_id=session.session_id,
                action_id=next_action.action_id,
                status=result_status,
                detail=detail,
                remaining_actions=remaining_actions,
                current_url=session.current_url,
                page_title=session.page_title,
                snapshot_summary=session.latest_snapshot_summary,
                available_target_count=len(session.available_targets),
                available_input_count=len(session.available_inputs),
                recovery_available=session.recovery_available,
                artifact_path=artifact_path,
            )
        except Exception as exc:
            session.executed_action_ids = [action_id for action_id in session.executed_action_ids if action_id != next_action.action_id]
            detail = f"Browser action '{next_action.action_id}' failed during provider execution: {exc}"
            return self._fail_action(session, next_action.action_id, detail, executed_at)

    def _fail_action(
        self,
        session: BrowserExecutionSession,
        action_id: str,
        detail: str,
        executed_at: str,
    ) -> BrowserActionExecutionResult:
        remaining_actions = len(session.planned_actions) - len(session.executed_action_ids)
        session.last_action_id = action_id
        session.last_action_detail = detail
        session.last_action_status = "blocked"
        session.last_failure_detail = detail
        session.status = "failed"
        self.append_event(session, kind="failed", detail=detail, created_at=executed_at)
        self._policy.refresh_pending_state(session)
        return BrowserActionExecutionResult(
            session_id=session.session_id,
            action_id=action_id,
            status="blocked",
            detail=detail,
            remaining_actions=remaining_actions,
            current_url=session.current_url,
            page_title=session.page_title,
            snapshot_summary=session.latest_snapshot_summary,
            available_target_count=len(session.available_targets),
            available_input_count=len(session.available_inputs),
            recovery_available=session.recovery_available,
            artifact_path=session.latest_artifact_path,
        )
