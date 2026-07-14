"""Generic webhook bridge channel for external IM connector projects."""

from __future__ import annotations

import logging
import secrets
import time
from pathlib import Path
from typing import Any

import httpx

from src.gateway.channels.base import Channel
from src.gateway.channels.message_bus import (
    InboundMessageType,
    MessageBus,
    OutboundMessage,
    ResolvedAttachment,
)

logger = logging.getLogger(__name__)


def _as_inbound_message_type(value: str | None) -> InboundMessageType:
    normalized = str(value or "chat").strip().lower()
    if normalized == "command":
        return InboundMessageType.COMMAND
    return InboundMessageType.CHAT


class ExternalBridgeChannel(Channel):
    """Bridge channel backed by an external IM connector process.

    The channel does not talk to the upstream IM platform directly. Instead it:
    1. Accepts inbound webhook pushes from an external bridge process.
    2. Sends outbound replies to the bridge's configured webhook endpoint.
    3. Exposes a small auth/status/logout contract when the bridge supports it.
    """

    def __init__(self, bus: MessageBus, config: dict[str, Any]) -> None:
        channel_name = str(config.get("channel_name") or "external_bridge").strip()
        super().__init__(name=channel_name, bus=bus, config=config)
        self._client: httpx.AsyncClient | None = None
        self._shared_secret = str(config.get("shared_secret") or "").strip()
        self._outbound_url = str(config.get("outbound_url") or "").strip() or None
        self._transport = str(config.get("transport") or "webhook_bridge").strip() or "webhook_bridge"
        self._allowed_users = {str(user_id).strip() for user_id in config.get("allowed_users", []) if str(user_id).strip()}
        self._timeout_seconds = float(config.get("timeout_seconds") or 20.0)
        self._platform_label = str(config.get("platform_label") or channel_name).strip()
        self._last_inbound_at: float | None = None
        self._last_outbound_at: float | None = None
        self._last_outbound_status: int | None = None
        self._last_outbound_error: str | None = None

    async def start(self) -> None:
        if self._running:
            return
        if not self._shared_secret:
            logger.error("[%s] bridge channel requires shared_secret", self.name)
            return

        self._client = httpx.AsyncClient(timeout=self._timeout_seconds)
        self._running = True
        self.bus.subscribe_outbound(self._on_outbound)
        logger.info("[%s] external bridge channel started", self.name)

    async def stop(self) -> None:
        self._running = False
        self.bus.unsubscribe_outbound(self._on_outbound)
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("[%s] external bridge channel stopped", self.name)

    async def get_login_qrcode(self) -> bytes | None:
        """Fetch the login QR code if the underlying bridge supports it."""
        for qrcode_path in self._qrcode_path_candidates():
            if not qrcode_path.exists():
                continue
            try:
                return qrcode_path.read_bytes()
            except Exception as exc:
                logger.warning("[%s] Failed to read QR code from %s: %s", self.name, qrcode_path, exc)
        return None

    def _qrcode_path_candidates(self) -> list[Path]:
        configured = str(self.config.get("qrcode_path") or "").strip()
        candidates = [Path(configured).expanduser()] if configured else []
        if self.name == "qq":
            repo_root = Path(__file__).resolve().parents[3]
            candidates.append(repo_root / "runtime/tools/napcat/opt/QQ/resources/app/app_launcher/napcat/cache/qrcode.png")
        return list(dict.fromkeys(candidates))

    def _status_url_candidates(self) -> list[str]:
        urls: list[str] = []
        for key in ("login_status_url", "identity_url", "bridge_identity_url"):
            value = str(self.config.get(key) or "").strip()
            if value:
                urls.append(value)
        if self.name == "qq":
            urls.extend(
                [
                    "http://127.0.0.1:30101/identity",
                    "http://127.0.0.1:3001/get_login_info",
                    "http://127.0.0.1:3000/get_login_info",
                ]
            )
        return list(dict.fromkeys(urls))

    async def _request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any] | None:
        close_client = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout_seconds)
            close_client = True
        try:
            resp = await client.request(method, url, **kwargs)
            if resp.status_code >= 400:
                return {"ok": False, "status_code": resp.status_code, "error": resp.text[:500]}
            data = resp.json()
            return data if isinstance(data, dict) else {"ok": True, "data": data}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            if close_client:
                await client.aclose()

    def _auth_status(self, **overrides: Any) -> dict[str, Any]:
        status = {
            "logged_in": False,
            "account_id": None,
            "display_name": None,
            "info": {},
            "bridge_ready": self._running,
            "outbound_ready": bool(self._outbound_url),
            "reply_ready": self._running and bool(self._outbound_url),
            "last_inbound_at": self._last_inbound_at,
            "last_outbound_at": self._last_outbound_at,
            "last_outbound_status": self._last_outbound_status,
            "last_outbound_error": self._last_outbound_error,
        }
        status.update(overrides)
        return status

    def _normalize_login_status(self, data: dict[str, Any], *, source: str) -> dict[str, Any]:
        info = data.get("info") if isinstance(data.get("info"), dict) else data.get("data") if isinstance(data.get("data"), dict) else {}
        account_id = str(info.get("user_id") or info.get("account_id") or data.get("user_id") or "").strip() or None
        display_name = str(info.get("nickname") or info.get("display_name") or info.get("name") or "").strip() or None
        return self._auth_status(
            logged_in=bool(account_id),
            account_id=account_id,
            display_name=display_name,
            info=info,
            source=source,
        )

    async def check_login_status(self) -> dict[str, Any]:
        """Check if the bridge has successfully logged in."""
        last_error = None
        for status_url in self._status_url_candidates():
            data = await self._request_json("GET", status_url)
            if not data:
                continue
            if data.get("logged_in") is True:
                return self._normalize_login_status(data, source=status_url)
            if data.get("status") == "ok" and isinstance(data.get("data"), dict):
                user_data = data.get("data") or {}
                if user_data.get("user_id"):
                    return self._normalize_login_status({"logged_in": True, "info": user_data}, source=status_url)
            if data.get("retcode") == 0 and isinstance(data.get("data"), dict):
                user_data = data.get("data") or {}
                if user_data.get("user_id"):
                    return self._normalize_login_status({"logged_in": True, "info": user_data}, source=status_url)
            if any(key in data for key in ("qrcode", "napcat_process", "napcat_status")):
                return self._auth_status(
                    logged_in=False,
                    source=status_url,
                    error=data.get("error") or data.get("message") or data.get("wording") or last_error,
                    qrcode=data.get("qrcode"),
                    napcat_process=data.get("napcat_process"),
                    napcat_status=data.get("napcat_status"),
                )
            last_error = data.get("error") or data.get("message") or data.get("wording") or last_error
        return self._auth_status(logged_in=False, error=last_error)

    async def get_auth_status(self) -> dict[str, Any]:
        status = await self.check_login_status()
        status.update(
            {
                "bridge_ready": self._running,
                "outbound_ready": bool(self._outbound_url),
                "reply_ready": self._running and bool(self._outbound_url) and bool(status.get("logged_in")),
                "last_inbound_at": self._last_inbound_at,
                "last_outbound_at": self._last_outbound_at,
                "last_outbound_status": self._last_outbound_status,
                "last_outbound_error": self._last_outbound_error,
            }
        )
        return status

    async def logout(self) -> dict[str, Any]:
        logout_url = str(self.config.get("logout_url") or "").strip()
        if not logout_url and self.name == "qq":
            logout_url = "http://127.0.0.1:30101/logout"
        if not logout_url:
            return {"success": True, "message": "Local channel configuration cleared; upstream logout is not configured."}
        data = await self._request_json("POST", logout_url, headers={"X-OctoAgent-Bridge-Token": self._shared_secret})
        if data and data.get("ok") is not False:
            return {"success": True, "message": data.get("message") or "Logout requested", "detail": data}
        return {"success": False, "message": (data or {}).get("error") or "Logout failed", "detail": data or {}}

    def accepts_shared_secret(self, shared_secret: str | None) -> bool:
        if not self._shared_secret:
            return False
        provided = str(shared_secret or "")
        return secrets.compare_digest(self._shared_secret, provided)

    async def publish_bridge_inbound(self, payload: dict[str, Any]) -> bool:
        user_id = str(payload.get("user_id") or "").strip()
        if self._allowed_users and user_id not in self._allowed_users:
            logger.warning("[%s] rejected inbound bridge user %s", self.name, user_id)
            return False

        chat_id = str(payload.get("chat_id") or "").strip()
        text = str(payload.get("text") or "").strip()
        if not chat_id or not user_id or (not text and not payload.get("files")):
            logger.warning("[%s] rejected malformed inbound bridge payload", self.name)
            return False

        inbound = self._make_inbound(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            msg_type=_as_inbound_message_type(payload.get("msg_type")),
            thread_ts=str(payload.get("thread_ts") or "").strip() or None,
            files=payload.get("files") if isinstance(payload.get("files"), list) else None,
            metadata={
                **(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
                "bridge_transport": self._transport,
                "platform_label": self._platform_label,
            },
        )
        inbound.topic_id = str(payload.get("topic_id") or "").strip() or inbound.thread_ts or inbound.chat_id
        self._last_inbound_at = time.time()
        await self.bus.publish_inbound(inbound)
        return True

    async def send(self, msg: OutboundMessage) -> None:
        if self._client is None or not self._outbound_url:
            logger.warning("[%s] outbound bridge skipped because outbound_url is not configured", self.name)
            return

        headers = {
            "Content-Type": "application/json",
            "X-OctoAgent-Bridge-Token": self._shared_secret,
        }
        outbound_payload = {
            "event": "outbound_message",
            "platform": self.name,
            "platform_label": self._platform_label,
            "chat_id": msg.chat_id,
            "thread_ts": msg.thread_ts,
            "thread_id": msg.thread_id,
            "text": msg.text,
            "is_final": msg.is_final,
            "metadata": msg.metadata,
        }
        try:
            response = await self._client.post(
                self._outbound_url,
                headers=headers,
                json=outbound_payload,
            )
            self._last_outbound_at = time.time()
            self._last_outbound_status = response.status_code
            response.raise_for_status()
            self._last_outbound_error = None
        except Exception as exc:
            self._last_outbound_at = time.time()
            self._last_outbound_error = str(exc)
            raise

    async def send_file(self, msg: OutboundMessage, attachment: ResolvedAttachment) -> bool:
        if self._client is None or not self._outbound_url:
            return False

        headers = {
            "Content-Type": "application/json",
            "X-OctoAgent-Bridge-Token": self._shared_secret,
        }
        payload = {
            "event": "outbound_attachment",
            "platform": self.name,
            "platform_label": self._platform_label,
            "chat_id": msg.chat_id,
            "thread_ts": msg.thread_ts,
            "thread_id": msg.thread_id,
            "filename": attachment.filename,
            "mime_type": attachment.mime_type,
            "size": attachment.size,
            "is_image": attachment.is_image,
            "virtual_path": attachment.virtual_path,
        }
        response = await self._client.post(
            self._outbound_url,
            headers=headers,
            json=payload,
        )
        self._last_outbound_at = time.time()
        self._last_outbound_status = response.status_code
        response.raise_for_status()
        return True
