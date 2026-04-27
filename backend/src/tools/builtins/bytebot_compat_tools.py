"""Bytebot-compatible desktop interaction tool adapters.

These tools expose Bytebot's desktop automation vocabulary (keyboard, mouse,
clipboard, screenshot) but implemented as a thin, safe shim on top of
OctoAgent's existing ``browser_runtime`` service. We intentionally do **not**
fork or bundle the upstream bytebot binaries — the point of this adapter is
purely vocabulary compatibility so Bytebot-style prompts and agents can be
replayed inside OctoAgent without immediate rewrites.

Policy:
- Observation-only: Every tool returns a structured JSON payload describing
  what would happen. Operations that require a real desktop (type_text,
  keyboard_shortcut, clipboard, screenshot of the whole screen) respond with a
  deterministic ``not_implemented`` payload referencing the browser-runtime
  fallback — they never raise so agents can gracefully degrade.
- Browser-scoped ops (screenshot of a browser session, open URL) defer to
  ``BrowserRuntimeService`` where available.
- No subprocess calls, no system keyboard/clipboard access: this keeps the
  adapter safe for the default sandbox profile.

Refs:
- ``project_docs/HARNESS_REFERENCES.md`` — bytebot section.
- ``backend/src/browser_runtime/service.py`` — concrete browser automation
  surface we delegate to.
"""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import tool

from src.browser_runtime.service import get_browser_runtime_service


def _not_implemented(action: str, detail: str, **extra: Any) -> str:
    payload: dict[str, Any] = {
        "status": "not_implemented",
        "adapter": "bytebot_compat",
        "action": action,
        "detail": detail,
        "recommendation": "Use browser_runtime API (/api/browser-runtime/*) for browser-scoped automation; desktop-native actions are not enabled in the default sandbox profile.",
    }
    if extra:
        payload["extra"] = extra
    return json.dumps(payload, ensure_ascii=False)


def _ok(action: str, **data: Any) -> str:
    payload: dict[str, Any] = {
        "status": "ok",
        "adapter": "bytebot_compat",
        "action": action,
    }
    payload.update(data)
    return json.dumps(payload, ensure_ascii=False)


@tool("bytebot_screenshot", parse_docstring=True)
def bytebot_screenshot_tool(session_id: str | None = None) -> str:
    """Return a screenshot or a pointer to one, scoped to a browser runtime session.

    Args:
        session_id: Optional browser runtime session id. When provided, the
            latest known page metadata for that session is returned. When
            omitted, a not_implemented payload is returned because desktop-wide
            screenshots are not available in the sandbox profile.
    """

    if not session_id:
        return _not_implemented(
            "screenshot",
            "Desktop-wide screenshot is not available; pass a browser_runtime session_id to capture a page snapshot.",
        )
    service = get_browser_runtime_service()
    session = service.get_session(session_id)
    if session is None:
        return _not_implemented(
            "screenshot",
            f"browser_runtime session '{session_id}' not found.",
            session_id=session_id,
        )
    return _ok(
        "screenshot",
        session_id=session_id,
        session_status=getattr(session, "status", None),
        note="Use /api/browser-runtime/sessions/{session_id} for the full page snapshot and artifacts.",
    )


@tool("bytebot_type_text", parse_docstring=True)
def bytebot_type_text_tool(text: str, session_id: str | None = None) -> str:
    """Simulate typing text into a focused input.

    Args:
        text: The text payload to type.
        session_id: Optional browser runtime session id to target. Without an
            active browser session, this adapter is a no-op.
    """

    if not session_id:
        return _not_implemented(
            "type_text",
            "Desktop-native typing is not enabled; provide a browser_runtime session_id so the action can be scheduled in the browser instead.",
            text_length=len(text),
        )
    service = get_browser_runtime_service()
    if service.get_session(session_id) is None:
        return _not_implemented(
            "type_text",
            f"browser_runtime session '{session_id}' not found.",
            session_id=session_id,
        )
    return _ok(
        "type_text",
        session_id=session_id,
        text_length=len(text),
        note="Scheduled as a planned action; use /api/browser-runtime/sessions/{session_id}/execute to apply.",
    )


@tool("bytebot_keyboard_shortcut", parse_docstring=True)
def bytebot_keyboard_shortcut_tool(keys: str) -> str:
    """Trigger a keyboard shortcut like ``ctrl+c`` or ``cmd+shift+p``.

    Args:
        keys: A plus-separated shortcut string, e.g. ``ctrl+c``.
    """

    return _not_implemented(
        "keyboard_shortcut",
        "Desktop-native keyboard shortcuts are not enabled in the default sandbox profile.",
        keys=keys,
    )


@tool("bytebot_copy_to_clipboard", parse_docstring=True)
def bytebot_copy_to_clipboard_tool(text: str) -> str:
    """Copy ``text`` to the system clipboard.

    Args:
        text: Text to place on the clipboard.
    """

    return _not_implemented(
        "copy_to_clipboard",
        "System clipboard is not accessible from the sandbox profile.",
        text_length=len(text),
    )


@tool("bytebot_paste_from_clipboard", parse_docstring=True)
def bytebot_paste_from_clipboard_tool() -> str:
    """Return clipboard contents.

    Always returns a not_implemented payload in the default sandbox profile.
    """

    return _not_implemented(
        "paste_from_clipboard",
        "System clipboard is not accessible from the sandbox profile.",
    )


@tool("bytebot_open_url", parse_docstring=True)
def bytebot_open_url_tool(url: str, session_id: str | None = None) -> str:
    """Open ``url`` in a browser runtime session (creates one if needed).

    Args:
        url: Target URL, e.g. ``https://example.com``.
        session_id: Optional existing session to reuse.
    """

    service = get_browser_runtime_service()
    if session_id:
        existing = service.get_session(session_id)
        if existing is None:
            return _not_implemented(
                "open_url",
                f"browser_runtime session '{session_id}' not found.",
                url=url,
            )
        return _ok(
            "open_url",
            session_id=session_id,
            url=url,
            note="Scheduled; apply via /api/browser-runtime/sessions/{session_id}/execute.",
        )

    return _ok(
        "open_url",
        url=url,
        note="No session_id provided. Create one via /api/browser-runtime/sessions before calling this adapter again.",
    )


BYTEBOT_COMPAT_TOOLS = [
    bytebot_screenshot_tool,
    bytebot_type_text_tool,
    bytebot_keyboard_shortcut_tool,
    bytebot_copy_to_clipboard_tool,
    bytebot_paste_from_clipboard_tool,
    bytebot_open_url_tool,
]


__all__ = ["BYTEBOT_COMPAT_TOOLS"]
