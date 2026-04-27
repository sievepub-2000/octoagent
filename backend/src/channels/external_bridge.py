"""Generic webhook bridge channel for external IM connector projects."""

from __future__ import annotations

import logging
import secrets
from typing import Any

import httpx

from src.channels.base import Channel
from src.channels.message_bus import (
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
    if normalized == "event":
        return InboundMessageType.EVENT
    return InboundMessageType.CHAT


class ExternalBridgeChannel(Channel):
    """Bridge channel backed by external GitHub connector projects.

    The channel does not talk to the upstream IM platform directly. Instead it:
    1. Accepts inbound webhook pushes from an external bridge process.
    2. Sends outbound replies to the bridge's configured webhook endpoint.
    """

    def __init__(self, bus: MessageBus, config: dict[str, Any]) -> None:
        channel_name = str(config.get("channel_name") or "external_bridge").strip()
        super().__init__(name=channel_name, bus=bus, config=config)
        self._client: httpx.AsyncClient | None = None
        self._shared_secret = str(config.get("shared_secret") or "").strip()
        self._outbound_url = str(config.get("outbound_url") or "").strip() or None
        self._transport = str(config.get("transport") or "webhook_bridge").strip() or "webhook_bridge"
        self._allowed_users = {
            str(user_id).strip()
            for user_id in config.get("allowed_users", [])
            if str(user_id).strip()
        }
        self._timeout_seconds = float(config.get("timeout_seconds") or 20.0)
        self._platform_label = str(config.get("platform_label") or channel_name).strip()

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
                **(
                    payload.get("metadata")
                    if isinstance(payload.get("metadata"), dict)
                    else {}
                ),
                "bridge_transport": self._transport,
                "platform_label": self._platform_label,
            },
        )
        inbound.topic_id = (
            str(payload.get("topic_id") or "").strip()
            or inbound.thread_ts
            or inbound.chat_id
        )
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
        response = await self._client.post(
            self._outbound_url,
            headers=headers,
            json=outbound_payload,
        )
        response.raise_for_status()

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
        response.raise_for_status()
        return True