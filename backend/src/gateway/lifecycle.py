"""Lifecycle for the single OctoAgent app-server process."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.gateway.config import get_gateway_config
from src.governance.about import initialize_internal_secrets
from src.runtime.config.app_config import get_app_config

logger = logging.getLogger(__name__)


def _initialize_configuration():
    try:
        initialize_internal_secrets(__import__("pathlib").Path(__file__).resolve().parents[3])
        get_app_config()
    except Exception as exc:
        logger.exception("Configuration initialization failed")
        raise RuntimeError(f"Failed to load configuration: {exc}") from exc
    config = get_gateway_config()
    logger.info("Starting OctoAgent app-server on %s:%s", config.host, config.port)
    return config


def _repair_runtime_permissions(app: FastAPI) -> None:
    try:
        from src.runtime.permissions import repair_runtime_write_permissions

        app.state.runtime_permission_repair = repair_runtime_write_permissions()
    except Exception:
        logger.exception("Runtime permission repair failed")


async def _start_channel_service() -> None:
    try:
        from src.gateway.channels.service import start_channel_service

        service = await start_channel_service()
        logger.info("Channel service started: %d connectors", len(service.get_status().get("channels", {})))
    except Exception:
        logger.exception("Channel service failed to start")


async def _stop_channel_service() -> None:
    try:
        from src.gateway.channels.service import stop_channel_service

        await stop_channel_service()
    except Exception:
        logger.exception("Channel service failed to stop")


async def _initialize_harness(app: FastAPI) -> None:
    """Recover Markdown memory, rebuild its vector index and refresh tools."""
    try:
        from src.harness.memory import get_harness_memory
        from src.utils.agent_tool_guide import generate_agent_tool_guide

        report = await asyncio.to_thread(get_harness_memory().initialize)
        report["tool_guide"] = str(await asyncio.to_thread(generate_agent_tool_guide))
        app.state.harness_memory = report
        logger.info("Harness initialized: %s", report)
    except Exception:
        logger.exception("Harness initialization failed")


def _start_oom_guard(app: FastAPI) -> None:
    try:
        from src.runtime.oom_guard import start_oom_guard_task

        start_oom_guard_task(app)
    except Exception:
        logger.exception("OOM guard failed to start")


async def _stop_oom_guard(app: FastAPI) -> None:
    try:
        from src.runtime.oom_guard import stop_oom_guard_task

        await stop_oom_guard_task(app)
    except Exception:
        logger.exception("OOM guard failed to stop")


@asynccontextmanager
async def gateway_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    _initialize_configuration()
    _repair_runtime_permissions(app)
    await _start_channel_service()
    await _initialize_harness(app)
    _start_oom_guard(app)
    yield
    await _stop_oom_guard(app)
    await _stop_channel_service()
    logger.info("OctoAgent app-server stopped")
