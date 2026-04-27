"""Gateway router for IM channel management."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from src.utils.agent_tool_guide import async_refresh_agent_tool_guide

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])


class ChannelStatusResponse(BaseModel):
    service_running: bool
    channels: dict[str, dict]


class ChannelRestartResponse(BaseModel):
    success: bool
    message: str


class ChannelConfigUpdateRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class ChannelConfigUpdateResponse(BaseModel):
    success: bool
    message: str
    channel: dict[str, Any]


class ChannelEnabledUpdateRequest(BaseModel):
    enabled: bool


class ChannelEnabledUpdateResponse(BaseModel):
    success: bool
    message: str
    channel: dict[str, Any]


class ChannelBridgeInboundRequest(BaseModel):
    chat_id: str
    user_id: str
    text: str = ""
    msg_type: str = "chat"
    thread_ts: str | None = None
    topic_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    files: list[dict[str, Any]] = Field(default_factory=list)


class ChannelBridgeInboundResponse(BaseModel):
    accepted: bool
    message: str


def _config_path() -> Path:
    from src.config.app_config import AppConfig

    return AppConfig.resolve_config_path()


def _load_config_data() -> dict[str, Any]:
    config_path = _config_path()
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def _write_config_data(config_data: dict[str, Any]) -> None:
    from src.config.app_config import reload_app_config

    config_path = _config_path()
    config_path.write_text(
        yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    reload_app_config(str(config_path))


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def _normalize_channel_value(field: dict[str, Any], value: Any) -> Any:
    kind = field.get("kind")
    if kind == "boolean":
        return _parse_bool(value)
    if kind == "string_list":
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [
                item.strip()
                for item in re.split(r"[\n,]+", value)
                if item.strip()
            ]
        return [str(value).strip()] if str(value).strip() else []
    if kind == "number":
        if value in (None, ""):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value) if value.is_integer() else value
        try:
            parsed = float(str(value).strip())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid numeric value for {field.get('name')}") from exc
        return int(parsed) if parsed.is_integer() else parsed
    if value is None:
        return ""
    return str(value).strip()


def _service_snapshot():
    from src.channels.service import ChannelService, get_channel_service

    service = get_channel_service()
    if service is not None:
        return service
    return ChannelService.from_app_config()


@router.get("/", response_model=ChannelStatusResponse)
async def get_channels_status() -> ChannelStatusResponse:
    """Get the status of all IM channels."""
    service = _service_snapshot()
    status = service.get_status()
    return ChannelStatusResponse(**status)


@router.put("/{name}/config", response_model=ChannelConfigUpdateResponse)
async def update_channel_config(
    name: str,
    request: ChannelConfigUpdateRequest,
) -> ChannelConfigUpdateResponse:
    """Persist a channel configuration block into config.yaml and reload the service."""
    from src.channels.service import (
        ChannelService,
        _channel_registry_entry,
        start_channel_service,
        stop_channel_service,
    )

    registry_entry = _channel_registry_entry(name)
    if not registry_entry:
        raise HTTPException(status_code=404, detail=f"Unknown channel '{name}'")

    fields = list(registry_entry.get("fields") or [])
    if not fields:
        raise HTTPException(status_code=400, detail=f"Channel '{name}' does not expose editable fields")

    editable_fields = {
        str(field.get("name") or "").strip(): field
        for field in fields
        if str(field.get("name") or "").strip()
    }
    config_data = _load_config_data()
    channels_config = dict(config_data.get("channels") or {})
    existing_config = dict(channels_config.get(name) or {})

    for key, raw_value in request.config.items():
        field = editable_fields.get(key)
        if field is None:
            continue
        existing_config[key] = _normalize_channel_value(field, raw_value)

    channels_config[name] = existing_config
    config_data["channels"] = channels_config
    _write_config_data(config_data)

    try:
        await stop_channel_service()
        service = await start_channel_service()
    except Exception:
        logger.exception("Failed to fully restart channel service after updating %s", name)
        service = ChannelService.from_app_config()

    status = service.get_status()
    channel_status = status.get("channels", {}).get(name)
    if not isinstance(channel_status, dict):
        raise HTTPException(status_code=500, detail=f"Failed to reload channel '{name}'")

    await async_refresh_agent_tool_guide()

    return ChannelConfigUpdateResponse(
        success=True,
        message=f"Channel {name} configuration saved",
        channel=channel_status,
    )


@router.delete("/{name}/config", response_model=ChannelConfigUpdateResponse)
async def delete_channel_config(name: str) -> ChannelConfigUpdateResponse:
    """Clear a channel's stored configuration and restart the channel service.

    This removes the channel's block from ``config.yaml`` entirely, which is
    the "delete" semantic surfaced by the WebUI channels page. The channel
    registry itself is static (handlers are coded) so this does not remove the
    channel definition — only its persisted credentials/settings.
    """
    from src.channels.service import (
        ChannelService,
        _channel_registry_entry,
        start_channel_service,
        stop_channel_service,
    )

    registry_entry = _channel_registry_entry(name)
    if not registry_entry:
        raise HTTPException(status_code=404, detail=f"Unknown channel '{name}'")

    config_data = _load_config_data()
    channels_config = dict(config_data.get("channels") or {})
    if name in channels_config:
        channels_config.pop(name, None)
        config_data["channels"] = channels_config
        _write_config_data(config_data)

    try:
        await stop_channel_service()
        service = await start_channel_service()
    except Exception:
        logger.exception("Failed to restart channel service after deleting %s", name)
        service = ChannelService.from_app_config()

    status = service.get_status()
    channel_status = status.get("channels", {}).get(name) or {}
    await async_refresh_agent_tool_guide()
    return ChannelConfigUpdateResponse(
        success=True,
        message=f"Channel {name} configuration cleared",
        channel=channel_status,
    )


@router.post("/{name}/restart", response_model=ChannelRestartResponse)
async def restart_channel(name: str) -> ChannelRestartResponse:
    """Restart a specific IM channel."""
    from src.channels.service import get_channel_service

    service = get_channel_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Channel service is not running")

    success = await service.restart_channel(name)
    if success:
        logger.info("Channel %s restarted successfully", name)
        return ChannelRestartResponse(success=True, message=f"Channel {name} restarted successfully")
    else:
        logger.warning("Failed to restart channel %s", name)
        return ChannelRestartResponse(success=False, message=f"Failed to restart channel {name}")


@router.put("/{name}/enabled", response_model=ChannelEnabledUpdateResponse)
async def update_channel_enabled(
    name: str,
    request: ChannelEnabledUpdateRequest,
) -> ChannelEnabledUpdateResponse:
    """Persist a channel enabled flag into config.yaml and reload the service."""
    from src.channels.service import (
        ChannelService,
        _channel_registry_entry,
        start_channel_service,
        stop_channel_service,
    )

    registry_entry = _channel_registry_entry(name)
    if not registry_entry:
        raise HTTPException(status_code=404, detail=f"Unknown channel '{name}'")

    config_data = _load_config_data()
    channels_config = dict(config_data.get("channels") or {})
    existing_config = dict(channels_config.get(name) or {})
    existing_config["enabled"] = request.enabled
    channels_config[name] = existing_config
    config_data["channels"] = channels_config
    _write_config_data(config_data)

    try:
        await stop_channel_service()
        service = await start_channel_service()
    except Exception:
        logger.exception("Failed to fully restart channel service after toggling %s", name)
        service = ChannelService.from_app_config()

    status = service.get_status()
    channel_status = status.get("channels", {}).get(name)
    if not isinstance(channel_status, dict):
        raise HTTPException(status_code=500, detail=f"Failed to reload channel '{name}'")

    await async_refresh_agent_tool_guide()

    return ChannelEnabledUpdateResponse(
        success=True,
        message=f"Channel {name} {'enabled' if request.enabled else 'disabled'}",
        channel=channel_status,
    )


@router.post("/{name}/ingest", response_model=ChannelBridgeInboundResponse)
async def ingest_channel_message(
    name: str,
    request: ChannelBridgeInboundRequest,
    bridge_token: str | None = Header(default=None, alias="X-OctoAgent-Bridge-Token"),
) -> ChannelBridgeInboundResponse:
    """Accept an inbound webhook payload from an external bridge connector."""
    from src.channels.service import get_channel_service

    service = get_channel_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Channel service is not running")

    try:
        accepted = await service.publish_bridge_inbound(
            name,
            request.model_dump(),
            bridge_token,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if not accepted:
        raise HTTPException(status_code=404, detail=f"Bridge channel {name} is not active")

    return ChannelBridgeInboundResponse(
        accepted=True,
        message=f"Inbound bridge payload accepted for {name}",
    )
