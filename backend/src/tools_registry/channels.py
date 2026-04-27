from __future__ import annotations

from typing import Any, cast

import yaml

from src.config.app_config import AppConfig

from .contracts import ToolRegistryChannelItem

CHANNEL_DESCRIPTIONS = {
    "feishu": "飞书/Lark IM — WebSocket 实时通道",
    "slack": "Slack — Socket Mode 实时通道",
    "telegram": "Telegram Bot — 长轮询通道",
}


class ToolRegistryChannelReader:
    def __init__(self, *, config_path_resolver=AppConfig.resolve_config_path):
        self._config_path_resolver = config_path_resolver

    def read(self) -> list[ToolRegistryChannelItem]:
        config_path = self._config_path_resolver()
        raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        data = cast(dict[str, Any], raw_data if isinstance(raw_data, dict) else {})
        raw_channels = data.get("channels")
        channels = cast(dict[str, Any], raw_channels if isinstance(raw_channels, dict) else {})

        items: list[ToolRegistryChannelItem] = []
        for channel_name in ["feishu", "slack", "telegram"]:
            raw_cfg = channels.get(channel_name)
            cfg = cast(dict[str, Any], raw_cfg if isinstance(raw_cfg, dict) else {})
            items.append(
                ToolRegistryChannelItem(
                    name=channel_name,
                    enabled=bool(cfg.get("enabled", False)),
                    description=CHANNEL_DESCRIPTIONS.get(channel_name, ""),
                )
            )
        return items
