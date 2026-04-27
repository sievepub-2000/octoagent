"""ChannelService — manages the lifecycle of all IM channels."""

from __future__ import annotations

import logging
from typing import Any

from src.channels.manager import ChannelManager
from src.channels.message_bus import MessageBus
from src.channels.store import ChannelStore

logger = logging.getLogger(__name__)


def _field(
    name: str,
    label: str,
    kind: str,
    *,
    description: str | None = None,
    placeholder: str | None = None,
    required: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "kind": kind,
        "description": description,
        "placeholder": placeholder,
        "required": required,
    }


def _feishu_fields() -> list[dict[str, Any]]:
    return [
        _field("enabled", "Enabled", "boolean", description="Start the Feishu connector with OctoAgent."),
        _field("app_id", "App ID", "text", description="Feishu/Lark app identifier.", required=True),
        _field(
            "app_secret",
            "App Secret",
            "secret",
            description="App secret used for websocket authentication.",
            required=True,
        ),
        _field(
            "verification_token",
            "Verification Token",
            "secret",
            description="Optional verification token for additional ingress validation.",
        ),
    ]


def _slack_fields() -> list[dict[str, Any]]:
    return [
        _field("enabled", "Enabled", "boolean", description="Start the Slack Socket Mode connector."),
        _field("bot_token", "Bot Token", "secret", description="Slack bot token.", required=True),
        _field("app_token", "App Token", "secret", description="Slack app-level Socket Mode token.", required=True),
        _field(
            "allowed_users",
            "Allowed Users",
            "string_list",
            description="Optional Slack user IDs allowed to talk to this channel. One per line or comma-separated.",
            placeholder="U01234567\nU07654321",
        ),
    ]


def _telegram_fields() -> list[dict[str, Any]]:
    return [
        _field("enabled", "Enabled", "boolean", description="Start the Telegram polling connector."),
        _field("bot_token", "Bot Token", "secret", description="Telegram bot token.", required=True),
        _field(
            "allowed_users",
            "Allowed Users",
            "string_list",
            description="Optional Telegram usernames or IDs allowed to talk to this channel. One per line or comma-separated.",
            placeholder="123456789\n@octoagent_user",
        ),
    ]


def _bridge_fields() -> list[dict[str, Any]]:
    return [
        _field("enabled", "Enabled", "boolean", description="Expose the bridge-backed channel to OctoAgent."),
        _field(
            "shared_secret",
            "Shared Secret",
            "secret",
            description="Secret expected in X-OctoAgent-Bridge-Token for inbound bridge calls.",
            required=True,
        ),
        _field(
            "outbound_url",
            "Outbound URL",
            "url",
            description="Optional relay endpoint used when OctoAgent pushes replies back to the bridge.",
            placeholder="https://bridge.example.com/outbound",
        ),
        _field(
            "allowed_users",
            "Allowed Users",
            "string_list",
            description="Optional allowlist for bridge-specific user IDs. One per line or comma-separated.",
        ),
        _field(
            "timeout_seconds",
            "Timeout Seconds",
            "number",
            description="Optional outbound webhook timeout in seconds.",
            placeholder="15",
        ),
    ]

# Channel name → registry metadata
_CHANNEL_REGISTRY: dict[str, dict[str, Any]] = {
    "feishu": {
        "import_path": "src.channels.feishu:FeishuChannel",
        "handler_path": "src.channels.feishu:FeishuChannel",
        "config_path": "channels.feishu",
        "integration_mode": "native",
        "platform_label": "Feishu/Lark",
        "transport": "websocket",
        "description": "Native Feishu/Lark websocket connector.",
        "required_keys": ["app_id", "app_secret"],
        "fields": _feishu_fields(),
    },
    "slack": {
        "import_path": "src.channels.slack:SlackChannel",
        "handler_path": "src.channels.slack:SlackChannel",
        "config_path": "channels.slack",
        "integration_mode": "native",
        "platform_label": "Slack",
        "transport": "socket_mode",
        "description": "Native Slack connector using Socket Mode.",
        "required_keys": ["bot_token", "app_token"],
        "fields": _slack_fields(),
    },
    "telegram": {
        "import_path": "src.channels.telegram:TelegramChannel",
        "handler_path": "src.channels.telegram:TelegramChannel",
        "config_path": "channels.telegram",
        "integration_mode": "native",
        "platform_label": "Telegram",
        "transport": "long_polling",
        "description": "Native Telegram connector using long polling.",
        "required_keys": ["bot_token"],
        "fields": _telegram_fields(),
    },
    "qq": {
        "import_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "handler_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "config_path": "channels.qq",
        "integration_mode": "external_bridge",
        "platform_label": "QQ",
        "transport": "webhook_bridge",
        "description": "Bridge-backed QQ connector relayed through an external webhook adapter.",
        "required_keys": ["shared_secret"],
        "bridge_project": "mamoe/mirai",
        "bridge_project_url": "https://github.com/mamoe/mirai",
        "fields": _bridge_fields(),
    },
    "wechat": {
        "import_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "handler_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "config_path": "channels.wechat",
        "integration_mode": "external_bridge",
        "platform_label": "WeChat",
        "transport": "webhook_bridge",
        "description": "Bridge-backed WeChat connector relayed through an external webhook adapter.",
        "required_keys": ["shared_secret"],
        "bridge_project": "wechaty/wechaty",
        "bridge_project_url": "https://github.com/wechaty/wechaty",
        "fields": _bridge_fields(),
    },
    "line": {
        "import_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "handler_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "config_path": "channels.line",
        "integration_mode": "external_bridge",
        "platform_label": "LINE",
        "transport": "webhook_bridge",
        "description": "Bridge-backed LINE connector relayed through an external webhook adapter.",
        "required_keys": ["shared_secret"],
        "bridge_project": "line/line-bot-sdk-python",
        "bridge_project_url": "https://github.com/line/line-bot-sdk-python",
        "fields": _bridge_fields(),
    },
    "kakaotalk": {
        "import_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "handler_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "config_path": "channels.kakaotalk",
        "integration_mode": "external_bridge",
        "platform_label": "KakaoTalk",
        "transport": "webhook_bridge",
        "description": "Bridge-backed KakaoTalk connector relayed through an external webhook adapter.",
        "required_keys": ["shared_secret"],
        "bridge_project": "storycraft/node-kakao",
        "bridge_project_url": "https://github.com/storycraft/node-kakao",
        "fields": _bridge_fields(),
    },
    "whatsapp": {
        "import_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "handler_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "config_path": "channels.whatsapp",
        "integration_mode": "external_bridge",
        "platform_label": "WhatsApp",
        "transport": "webhook_bridge",
        "description": "Bridge-backed WhatsApp connector relayed through an external webhook adapter.",
        "required_keys": ["shared_secret"],
        "bridge_project": "open-wa/wa-automate-nodejs",
        "bridge_project_url": "https://github.com/open-wa/wa-automate-nodejs",
        "fields": _bridge_fields(),
    },
    "zalo": {
        "import_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "handler_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "config_path": "channels.zalo",
        "integration_mode": "external_bridge",
        "platform_label": "Zalo",
        "transport": "webhook_bridge",
        "description": "Bridge-backed Zalo connector relayed through an external webhook adapter.",
        "required_keys": ["shared_secret"],
        "bridge_project": "zaloplatform/zalo-php-sdk",
        "bridge_project_url": "https://github.com/zaloplatform/zalo-php-sdk",
        "fields": _bridge_fields(),
    },
    "facebook_messenger": {
        "import_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "handler_path": "src.channels.external_bridge:ExternalBridgeChannel",
        "config_path": "channels.facebook_messenger",
        "integration_mode": "external_bridge",
        "platform_label": "Facebook Messenger",
        "transport": "webhook_bridge",
        "description": "Bridge-backed Facebook Messenger connector relayed through an external webhook adapter.",
        "required_keys": ["shared_secret"],
        "bridge_project": "fbsamples/messenger-platform-samples",
        "bridge_project_url": "https://github.com/fbsamples/messenger-platform-samples",
        "fields": _bridge_fields(),
    },
}


def _channel_registry_entry(name: str) -> dict[str, Any]:
    return dict(_CHANNEL_REGISTRY.get(name) or {})


def _is_configured(config: dict[str, Any], required_keys: list[str]) -> bool:
    if not required_keys:
        return True
    return all(bool(str(config.get(key) or "").strip()) for key in required_keys)


def _serialize_channel_config(
    config: dict[str, Any] | None,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    source = config if isinstance(config, dict) else {}
    for field in fields:
        key = str(field.get("name") or "").strip()
        if not key:
            continue
        raw_value = source.get(key)
        kind = field.get("kind")
        if kind == "boolean":
            values[key] = bool(raw_value)
            continue
        if kind == "string_list":
            if isinstance(raw_value, list):
                values[key] = [str(item).strip() for item in raw_value if str(item).strip()]
            elif isinstance(raw_value, str):
                values[key] = [item.strip() for item in raw_value.replace(",", "\n").splitlines() if item.strip()]
            else:
                values[key] = []
            continue
        if kind == "number":
            values[key] = raw_value if isinstance(raw_value, (int, float)) else None
            continue
        values[key] = "" if raw_value is None else str(raw_value)
    return values


class ChannelService:
    """Manages the lifecycle of all configured IM channels.

    Reads configuration from ``config.yaml`` under the ``channels`` key,
    instantiates enabled channels, and starts the ChannelManager dispatcher.
    """

    def __init__(self, channels_config: dict[str, Any] | None = None) -> None:
        self.bus = MessageBus()
        self.store = ChannelStore()
        config = dict(channels_config or {})
        langgraph_url = config.pop("langgraph_url", None) or "http://localhost:19884"
        gateway_url = config.pop("gateway_url", None) or "http://localhost:19882"
        default_session = config.pop("session", None)
        channel_sessions = {
            name: channel_config.get("session")
            for name, channel_config in config.items()
            if isinstance(channel_config, dict)
        }
        self.manager = ChannelManager(
            bus=self.bus,
            store=self.store,
            langgraph_url=langgraph_url,
            gateway_url=gateway_url,
            default_session=default_session if isinstance(default_session, dict) else None,
            channel_sessions=channel_sessions,
        )
        self._channels: dict[str, Any] = {}  # name -> Channel instance
        self._config = config
        self._running = False

    @classmethod
    def from_app_config(cls) -> ChannelService:
        """Create a ChannelService from the application config."""
        from src.config.app_config import get_app_config

        config = get_app_config()
        channels_config = {}
        # extra fields are allowed by AppConfig (extra="allow")
        extra = config.model_extra or {}
        if "channels" in extra:
            channels_config = extra["channels"]
        return cls(channels_config=channels_config)

    async def start(self) -> None:
        """Start the manager and all enabled channels."""
        if self._running:
            return

        await self.manager.start()

        for name, channel_config in self._config.items():
            if not isinstance(channel_config, dict):
                continue
            if not channel_config.get("enabled", False):
                logger.info("Channel %s is disabled, skipping", name)
                continue

            await self._start_channel(name, channel_config)

        self._running = True
        logger.info("ChannelService started with channels: %s", list(self._channels.keys()))

    async def stop(self) -> None:
        """Stop all channels and the manager."""
        for name, channel in list(self._channels.items()):
            try:
                await channel.stop()
                logger.info("Channel %s stopped", name)
            except Exception:
                logger.exception("Error stopping channel %s", name)
        self._channels.clear()

        await self.manager.stop()
        self._running = False
        logger.info("ChannelService stopped")

    async def restart_channel(self, name: str) -> bool:
        """Restart a specific channel. Returns True if successful."""
        if name in self._channels:
            try:
                await self._channels[name].stop()
            except Exception:
                logger.exception("Error stopping channel %s for restart", name)
            del self._channels[name]

        config = self._config.get(name)
        if not config or not isinstance(config, dict):
            logger.warning("No config for channel %s", name)
            return False

        return await self._start_channel(name, config)

    async def _start_channel(self, name: str, config: dict[str, Any]) -> bool:
        """Instantiate and start a single channel."""
        registry_entry = _channel_registry_entry(name)
        import_path = registry_entry.get("import_path")
        if not import_path:
            logger.warning("Unknown channel type: %s", name)
            return False

        try:
            from src.reflection import resolve_class

            channel_cls = resolve_class(import_path, base_class=None)
        except Exception:
            logger.exception("Failed to import channel class for %s", name)
            return False

        try:
            channel_config = dict(config)
            channel_config.setdefault("channel_name", name)
            channel_config.setdefault("platform_label", registry_entry.get("platform_label", name))
            channel_config.setdefault("transport", registry_entry.get("transport", "unknown"))
            if registry_entry.get("bridge_project"):
                channel_config.setdefault("bridge_project", registry_entry["bridge_project"])
            if registry_entry.get("bridge_project_url"):
                channel_config.setdefault("bridge_project_url", registry_entry["bridge_project_url"])
            channel = channel_cls(bus=self.bus, config=channel_config)
            await channel.start()
            self._channels[name] = channel
            logger.info("Channel %s started", name)
            return True
        except Exception:
            logger.exception("Failed to start channel %s", name)
            return False

    def get_status(self) -> dict[str, Any]:
        """Return status information for all channels."""
        channels_status = {}
        for name, registry_entry in _CHANNEL_REGISTRY.items():
            config = self._config.get(name, {})
            fields = [dict(field) for field in list(registry_entry.get("fields") or [])]
            enabled = isinstance(config, dict) and config.get("enabled", False)
            running = name in self._channels and self._channels[name].is_running
            configured = isinstance(config, dict) and _is_configured(
                config,
                list(registry_entry.get("required_keys") or []),
            )
            channels_status[name] = {
                "enabled": enabled,
                "configured": configured,
                "running": running,
                "healthy": running and configured,
                "integration_mode": registry_entry.get("integration_mode", "native"),
                "platform_label": registry_entry.get("platform_label", name),
                "transport": registry_entry.get("transport", "unknown"),
                "description": registry_entry.get("description"),
                "config_path": registry_entry.get("config_path"),
                "handler_path": registry_entry.get("handler_path") or registry_entry.get("import_path"),
                "fields": fields,
                "config": _serialize_channel_config(config if isinstance(config, dict) else {}, fields),
                "bridge_project": registry_entry.get("bridge_project"),
                "bridge_project_url": registry_entry.get("bridge_project_url"),
                "ingest_path": f"/api/channels/{name}/ingest"
                if registry_entry.get("integration_mode") == "external_bridge"
                else None,
                "outbound_configured": bool(
                    isinstance(config, dict) and str(config.get("outbound_url") or "").strip()
                ),
            }
        return {
            "service_running": self._running,
            "channels": channels_status,
        }

    async def publish_bridge_inbound(self, name: str, payload: dict[str, Any], shared_secret: str | None) -> bool:
        """Publish an inbound message for a bridge-backed channel."""
        registry_entry = _channel_registry_entry(name)
        if registry_entry.get("integration_mode") != "external_bridge":
            return False

        channel = self._channels.get(name)
        if channel is None:
            return False

        accepts_secret = getattr(channel, "accepts_shared_secret", None)
        if callable(accepts_secret) and not accepts_secret(shared_secret):
            raise PermissionError("Invalid bridge shared secret")

        publish = getattr(channel, "publish_bridge_inbound", None)
        if not callable(publish):
            return False
        return bool(await publish(payload))


# -- singleton access -------------------------------------------------------

_channel_service: ChannelService | None = None


def get_channel_service() -> ChannelService | None:
    """Get the singleton ChannelService instance (if started)."""
    return _channel_service


async def start_channel_service() -> ChannelService:
    """Create and start the global ChannelService from app config."""
    global _channel_service
    if _channel_service is not None:
        return _channel_service
    _channel_service = ChannelService.from_app_config()
    await _channel_service.start()
    return _channel_service


async def stop_channel_service() -> None:
    """Stop the global ChannelService."""
    global _channel_service
    if _channel_service is not None:
        await _channel_service.stop()
        _channel_service = None
