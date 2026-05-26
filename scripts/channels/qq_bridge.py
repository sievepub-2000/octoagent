#!/usr/bin/env python3
"""QQ Bridge: NapCatQQ (OneBot v11) <-> OctoAgent Bridge Channel."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, ClientTimeout, web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [QQBridge] %(levelname)s %(message)s",
)
log = logging.getLogger("qq_bridge")

OCTO_BASE_URL = os.environ.get("OCTO_BASE_URL", "http://127.0.0.1:19800").rstrip("/")
BRIDGE_SECRET = os.environ.get("QQ_BRIDGE_SHARED_SECRET", "change-me")
NAPCAT_API_URL = os.environ.get("NAPCAT_API_URL", "http://127.0.0.1:19884").rstrip("/")
NAPCAT_API_FALLBACK_URLS = [
    item.rstrip("/")
    for item in os.environ.get("NAPCAT_API_FALLBACK_URLS", "http://127.0.0.1:19884").split(",")
    if item.strip()
]
NAPCAT_TOKEN = os.environ.get("NAPCAT_TOKEN", "")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "19814"))
MAX_QQ_MSG_LEN = int(os.environ.get("MAX_QQ_MSG_LEN", "4000"))
REPO_ROOT = Path(__file__).resolve().parents[2]
NAPCAT_QRCODE_PATH = Path(
    os.environ.get(
        "NAPCAT_QRCODE_PATH",
        REPO_ROOT / "runtime/tools/napcat/opt/QQ/resources/app/app_launcher/napcat/cache/qrcode.png",
    )
)
NAPCAT_PID_FILE = Path(os.environ.get("NAPCAT_PID_FILE", REPO_ROOT / "runtime/pids/napcat.pid"))

LAST_INBOUND: dict[str, Any] | None = None
LAST_OUTBOUND: dict[str, Any] | None = None
LAST_OUTBOUND_ERROR: str | None = None


def _napcat_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if NAPCAT_TOKEN:
        headers["Authorization"] = f"Bearer {NAPCAT_TOKEN}"
    return headers


def _split_message(text: str, limit: int = 4000) -> list[str]:
    """Split long messages into chunks for QQ."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        idx = text.rfind("\n", 0, limit)
        if idx < limit // 2:
            idx = limit
        chunks.append(text[:idx])
        text = text[idx:].lstrip("\n")
    return chunks


async def _call_napcat(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    urls = list(dict.fromkeys([NAPCAT_API_URL, *NAPCAT_API_FALLBACK_URLS]))
    timeout = ClientTimeout(total=10)
    async with ClientSession(timeout=timeout) as session:
        for base_url in urls:
            try:
                resp = await session.post(
                    f"{base_url}/{action}",
                    json=payload or {},
                    headers=_napcat_headers(),
                )
                text = await resp.text()
                try:
                    data = json.loads(text) if text else {}
                except Exception:
                    data = {"raw": text}
                if isinstance(data, dict):
                    data.setdefault("http_status", resp.status)
                    data.setdefault("source", base_url)
                    return data
                return {"http_status": resp.status, "data": data, "source": base_url}
            except Exception as exc:
                errors.append(f"{base_url}: {exc}")
    return {"ok": False, "error": "; ".join(errors) or "NapCat API unavailable", "sources": urls}


def _qrcode_info() -> dict[str, Any]:
    if not NAPCAT_QRCODE_PATH.exists():
        return {"available": False, "path": str(NAPCAT_QRCODE_PATH)}
    stat = NAPCAT_QRCODE_PATH.stat()
    return {
        "available": True,
        "path": str(NAPCAT_QRCODE_PATH),
        "mtime": stat.st_mtime,
        "age_seconds": max(0, int(time.time() - stat.st_mtime)),
        "api_path": "/api/channels/qq/qrcode",
    }


def _napcat_process_info() -> dict[str, Any]:
    if not NAPCAT_PID_FILE.exists():
        return {"running": False, "pid_file": str(NAPCAT_PID_FILE)}
    raw_pid = NAPCAT_PID_FILE.read_text(encoding="utf-8", errors="ignore").strip()
    if not raw_pid.isdigit():
        return {"running": False, "pid_file": str(NAPCAT_PID_FILE), "pid": raw_pid}
    return {"running": Path(f"/proc/{raw_pid}").exists(), "pid_file": str(NAPCAT_PID_FILE), "pid": int(raw_pid)}


async def handle_qq_inbound(request: web.Request) -> web.Response:
    """Receive NapCatQQ OneBot v11 event reports."""
    global LAST_INBOUND
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": True})

    post_type = data.get("post_type")
    if post_type != "message":
        return web.json_response({"ok": True})

    msg_type = data.get("message_type")
    user_id = str(data.get("user_id", ""))
    raw_msg = data.get("raw_message", "") or data.get("message", "")
    group_id = str(data.get("group_id", "")) if msg_type == "group" else ""
    message_id = str(data.get("message_id", ""))

    chat_id = group_id if group_id else user_id
    topic_id = f"qq_{chat_id}"

    text = str(raw_msg).strip() if isinstance(raw_msg, str) else str(raw_msg)
    if not text:
        return web.json_response({"ok": True})

    payload = {
        "chat_id": chat_id,
        "user_id": user_id,
        "text": text,
        "msg_type": "chat",
        "topic_id": topic_id,
        "metadata": {
            "qq_message_type": msg_type,
            "qq_group_id": group_id,
            "qq_message_id": message_id,
        },
    }

    LAST_INBOUND = {
        "at": time.time(),
        "user_id": user_id,
        "chat_id": chat_id,
        "message_type": msg_type,
        "message_id": message_id,
    }
    log.info("Inbound: user=%s chat=%s text=%s", user_id, chat_id, text[:80])

    try:
        timeout = ClientTimeout(total=120)
        async with ClientSession(timeout=timeout) as session:
            resp = await session.post(
                f"{OCTO_BASE_URL}/api/channels/qq/ingest",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-OctoAgent-Bridge-Token": BRIDGE_SECRET,
                },
            )
            log.info("OctoAgent response: status=%s", resp.status)
    except Exception:
        log.exception("Failed to forward to OctoAgent")

    return web.json_response({"ok": True})


async def handle_outbound(request: web.Request) -> web.Response:
    """Receive OctoAgent replies and send to QQ via NapCat OneBot API."""
    global LAST_OUTBOUND, LAST_OUTBOUND_ERROR
    token = request.headers.get("X-OctoAgent-Bridge-Token", "")
    if token != BRIDGE_SECRET:
        return web.json_response({"error": "forbidden"}, status=403)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": True})

    event = data.get("event", "")
    if event != "outbound_message":
        log.info("Ignoring outbound event: %s", event)
        return web.json_response({"ok": True})

    chat_id = str(data.get("chat_id", ""))
    text = str(data.get("text", ""))
    metadata = data.get("metadata") or {}
    qq_group_id = metadata.get("qq_group_id", "")

    if not text or not chat_id:
        return web.json_response({"ok": True})

    chunks = _split_message(text, MAX_QQ_MSG_LEN)
    log.info("Outbound: chat=%s chunks=%d total_len=%d", chat_id, len(chunks), len(text))

    try:
        timeout = ClientTimeout(total=15)
        async with ClientSession(timeout=timeout) as session:
            for chunk in chunks:
                if qq_group_id:
                    api_payload = {
                        "message_type": "group",
                        "group_id": int(qq_group_id),
                        "message": chunk,
                    }
                else:
                    api_payload = {
                        "message_type": "private",
                        "user_id": int(chat_id),
                        "message": chunk,
                    }
                resp = await session.post(
                    f"{NAPCAT_API_URL}/send_msg",
                    json=api_payload,
                    headers=_napcat_headers(),
                )
                body = await resp.text()
                log.info("NapCat send result: status=%s body=%s", resp.status, body[:160])
                LAST_OUTBOUND = {"at": time.time(), "chat_id": chat_id, "status": resp.status, "body": body[:500]}
                LAST_OUTBOUND_ERROR = None if 200 <= resp.status < 300 else body[:500]
                if resp.status >= 400:
                    return web.json_response({"accepted": False, "error": body[:500]}, status=502)
                if len(chunks) > 1:
                    await asyncio.sleep(0.5)
    except Exception as exc:
        LAST_OUTBOUND_ERROR = str(exc)
        log.exception("Failed to send to NapCat")
        return web.json_response({"accepted": False, "error": LAST_OUTBOUND_ERROR}, status=502)

    return web.json_response({"accepted": True})


async def handle_identity(request: web.Request) -> web.Response:
    login = await _call_napcat("get_login_info")
    status = await _call_napcat("get_status")

    data = login.get("data") if isinstance(login.get("data"), dict) else {}
    user_id = data.get("user_id")
    error = None if user_id else login.get("error") or login.get("message") or status.get("error")
    return web.json_response(
        {
            "logged_in": bool(user_id),
            "info": data,
            "account_id": str(user_id) if user_id else None,
            "display_name": data.get("nickname"),
            "bridge_ready": True,
            "napcat_process": _napcat_process_info(),
            "napcat_status": status,
            "qrcode": _qrcode_info(),
            "error": error,
            "last_inbound": LAST_INBOUND,
            "last_outbound": LAST_OUTBOUND,
            "last_outbound_error": LAST_OUTBOUND_ERROR,
        }
    )


async def handle_logout(request: web.Request) -> web.Response:
    token = request.headers.get("X-OctoAgent-Bridge-Token", "")
    if token and token != BRIDGE_SECRET:
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)
    try:
        result = await _call_napcat("bot_exit")
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=502)
    return web.json_response({"ok": True, "message": "NapCat bot_exit requested", "detail": result})


async def handle_diagnostics(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "ok": True,
            "service": "qq-bridge",
            "octo_base_url": OCTO_BASE_URL,
            "napcat_api_url": NAPCAT_API_URL,
              "napcat_api_fallback_urls": NAPCAT_API_FALLBACK_URLS,
              "napcat_process": _napcat_process_info(),
              "qrcode": _qrcode_info(),
            "last_inbound": LAST_INBOUND,
            "last_outbound": LAST_OUTBOUND,
            "last_outbound_error": LAST_OUTBOUND_ERROR,
        }
    )


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "qq-bridge"})


def main() -> None:
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/identity", handle_identity)
    app.router.add_get("/diagnostics", handle_diagnostics)
    app.router.add_post("/logout", handle_logout)
    app.router.add_post("/qq/inbound", handle_qq_inbound)
    app.router.add_post("/outbound", handle_outbound)
    log.info("QQ Bridge starting on port %d -> OctoAgent %s", LISTEN_PORT, OCTO_BASE_URL)
    web.run_app(app, host="127.0.0.1", port=LISTEN_PORT, print=None)


if __name__ == "__main__":
    main()
