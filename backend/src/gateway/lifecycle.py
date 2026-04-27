from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.architecture import get_service_bus
from src.config.app_config import get_app_config
from src.gateway.config import get_gateway_config
from src.system_guard.service import get_system_guard_service

logger = logging.getLogger(__name__)


def _initialize_configuration():
    try:
        get_app_config()
        logger.info("Configuration loaded successfully")
    except Exception as exc:
        error_msg = f"Failed to load configuration during gateway startup: {exc}"
        logger.exception(error_msg)
        raise RuntimeError(error_msg) from exc
    config = get_gateway_config()
    logger.info("Starting API Gateway on %s:%s", config.host, config.port)
    return config


def _initialize_system_guard(app: FastAPI) -> None:
    try:
        system_guard = get_system_guard_service()
        startup_report = system_guard.startup_check_and_repair()
        logger.info("System guard startup report: %s", startup_report)
        app.state.system_guard = system_guard
    except Exception:
        logger.exception("System guard startup check failed")


def _initialize_service_bus(app: FastAPI, config) -> None:
    try:
        bus = get_service_bus()
        bus.register("system_guard", getattr(app.state, "system_guard", None))
        bus.register("app_config", get_app_config())
        bus.register("gateway_config", config)
        app.state.service_bus = bus
        logger.info("ServiceBus initialized with services: %s", bus.registered)
    except Exception:
        logger.exception("ServiceBus initialization failed")


async def _start_channel_service() -> None:
    try:
        from src.channels.service import start_channel_service

        channel_service = await start_channel_service()
        logger.info("Channel service started: %s", channel_service.get_status())
    except Exception:
        logger.exception("No IM channels configured or channel service failed to start")


def _register_reflection_hooks() -> None:
    try:
        from src.reflection.skill_evolution_bridge import register_reflection_hooks

        register_reflection_hooks()
    except Exception:
        logger.exception("Failed to register reflection→skill_evolution hooks")


def _start_memory_cleanup_scheduler() -> None:
    """Start the background memory TTL/confidence/cap cleanup scheduler."""
    try:
        from src.agents.memory.cleanup import start_cleanup_scheduler

        start_cleanup_scheduler()
        logger.info("Memory cleanup scheduler started")
    except Exception:
        logger.exception("Failed to start memory cleanup scheduler")


def _start_runtime_maintenance_scheduler(app: FastAPI) -> None:
    try:
        from src.runtime_governance import get_runtime_maintenance_scheduler

        scheduler = get_runtime_maintenance_scheduler()
        scheduler.start()
        app.state.runtime_maintenance_scheduler = scheduler
        logger.info("Runtime maintenance scheduler started: %s", scheduler.status())
    except Exception:
        logger.exception("Failed to start runtime maintenance scheduler")




def _start_generic_agent(app: FastAPI) -> None:
    try:
        from src.generic_agent import start_generic_agent

        agent = start_generic_agent()
        app.state.generic_agent = agent
        if agent is not None:
            logger.info("Generic maintenance agent started: %s", agent.status())
    except Exception:
        logger.exception("Failed to start generic maintenance agent")


async def _shutdown_generic_agent(app: FastAPI) -> None:
    try:
        from src.generic_agent import stop_generic_agent

        stop_generic_agent()
        app.state.generic_agent = None
        logger.info("Generic maintenance agent stopped")
    except Exception:
        logger.exception("Failed to stop generic maintenance agent")


def _recover_orphaned_task_workspaces() -> None:
    try:
        import asyncio as _startup_asyncio

        from src.gateway.routers.task_workspaces import _merge_workspace_metadata
        from src.workflow_core import TaskWorkflowModule, recoverable_orphaned_workspaces, safe_auto_execute_workspace

        orphaned = recoverable_orphaned_workspaces()
        if orphaned:
            logger.info(
                "Recovering %d orphaned 'running' task workspace(s) on startup: %s",
                len(orphaned),
                [ws.task_id for ws in orphaned],
            )
            for ws in orphaned:
                _startup_asyncio.create_task(
                    safe_auto_execute_workspace(
                        ws,
                        merge_workspace_metadata=_merge_workspace_metadata,
                        workflow_module_factory=TaskWorkflowModule,
                    )
                )
        else:
            logger.info("No orphaned task workspaces to recover on startup.")
    except Exception:
        logger.exception("Failed to recover orphaned task workspaces on startup")


async def _shutdown_channel_service() -> None:
    try:
        from src.channels.service import stop_channel_service

        await stop_channel_service()
    except Exception:
        logger.exception("Failed to stop channel service")


def _shutdown_system_guard(app: FastAPI) -> None:
    try:
        system_guard = getattr(app.state, "system_guard", None)
        if system_guard is not None:
            report = system_guard.shutdown(reason="graceful_shutdown")
            logger.info("System guard shutdown report: %s", report)
    except Exception:
        logger.exception("Failed to persist system guard shutdown state")


async def _shutdown_runtime_maintenance_scheduler(app: FastAPI) -> None:
    try:
        scheduler = getattr(app.state, "runtime_maintenance_scheduler", None)
        if scheduler is not None:
            await scheduler.stop()
            logger.info("Runtime maintenance scheduler stopped")
    except Exception:
        logger.exception("Failed to stop runtime maintenance scheduler")


@asynccontextmanager
async def gateway_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    config = _initialize_configuration()
    _initialize_system_guard(app)
    _initialize_service_bus(app, config)
    await _start_channel_service()
    _recover_orphaned_task_workspaces()
    _register_reflection_hooks()
    _start_memory_cleanup_scheduler()
    _start_runtime_maintenance_scheduler(app)
    _start_generic_agent(app)
    yield
    await _shutdown_generic_agent(app)
    await _shutdown_runtime_maintenance_scheduler(app)
    await _shutdown_channel_service()
    _shutdown_system_guard(app)
    logger.info("Shutting down API Gateway")
