from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.gateway.config import get_gateway_config
from src.governance.about import initialize_internal_secrets as _init_internal_secrets
from src.harness import (
    init_run_journal,
    mark_orphans_on_startup,
    shutdown_run_journal,
    start_orphan_run_sweeper_task,
    stop_orphan_run_sweeper_task,
    sweep_orphaned_runs_once,
)
from src.harness.dispatcher import start_dispatcher_task, stop_dispatcher_task
from src.runtime.architecture import get_service_bus
from src.runtime.config.app_config import get_app_config
from src.runtime.system_guard.service import get_system_guard_service

logger = logging.getLogger(__name__)

# Process-scoped at-most-once guard for startup orphan recovery (see durable_execution).
_ORPHAN_RECOVERY_RUNNER = None


def _initialize_configuration():
    try:
        from src.governance.model_auth import initialize_model_auth_env

        initialize_model_auth_env()
        _init_internal_secrets(__import__('pathlib').Path(__file__).resolve().parents[3])
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


def _repair_runtime_permissions(app: FastAPI) -> None:
    try:
        from src.runtime.permissions import repair_runtime_write_permissions

        report = repair_runtime_write_permissions()
        app.state.runtime_permission_repair = report
    except Exception:
        logger.exception("Runtime permission repair failed")


def _initialize_runtime_config(app: FastAPI) -> None:
    try:
        from src.runtime.config.effective import initialize_runtime_config, rag_config_path

        app.state.rag_config = initialize_runtime_config()
        logger.info("Runtime RAG config applied from %s", rag_config_path())
    except Exception:
        logger.exception("Runtime config initialization failed")


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
        from src.gateway.channels.service import start_channel_service

        channel_service = await start_channel_service()
        status = channel_service.get_status()
        logger.debug("Channel service started: %s", status)
        logger.info("Channel service started: %d connectors loaded", len(status.get("channels", {})))
    except Exception:
        logger.exception("No IM channels configured or channel service failed to start")


def _register_reflection_hooks() -> None:
    try:
        from src.harness.reflection.skill_evolution_bridge import register_reflection_hooks

        register_reflection_hooks()
    except Exception:
        logger.exception("Failed to register reflection→skill_evolution hooks")


def _start_memory_cleanup_scheduler() -> None:
    """Start the background memory TTL/confidence/cap cleanup scheduler."""
    try:
        from src.agents.memory.cleanup import start_cleanup_scheduler

        start_cleanup_scheduler()
        logger.info("Memory cleanup scheduler started")
        try:
            from src.storage.self_evolution.dynamic_tools import register_hook_listener

            register_hook_listener()
        except Exception as exc:
            logger.debug("Dynamic-tools hook listener skipped: %s", exc)

    except Exception:
        logger.exception("Failed to start memory cleanup scheduler")


def _start_runtime_maintenance_scheduler(app: FastAPI) -> None:
    try:
        from src.runtime.governance import get_runtime_maintenance_scheduler

        scheduler = get_runtime_maintenance_scheduler()
        scheduler.start()
        app.state.runtime_maintenance_scheduler = scheduler
        logger.info("Runtime maintenance scheduler started: %s", scheduler.status())
        # Sprint-3: AutoProducer (lessons -> EvolutionProposal). Default OFF.
        try:
            from src.storage.self_evolution.producer import get_default_producer

            _auto_producer = get_default_producer()
            _auto_producer.start()
            logger.info("AutoProducer registered (enabled=%s)", bool(_auto_producer._task))
        except Exception as exc:
            logger.warning("AutoProducer registration failed: %s", exc)

    except Exception:
        logger.exception("Failed to start runtime maintenance scheduler")


def _start_oom_guard(app: FastAPI) -> None:
    try:
        from src.runtime.oom_guard import start_oom_guard_task

        start_oom_guard_task(app)
        logger.info("OOM guard started")
    except Exception:
        logger.exception("Failed to start OOM guard")


async def _shutdown_oom_guard(app: FastAPI) -> None:
    try:
        from src.runtime.oom_guard import stop_oom_guard_task

        await stop_oom_guard_task(app)
        logger.info("OOM guard stopped")
    except Exception:
        logger.exception("Failed to stop OOM guard")


def _start_generic_agent(app: FastAPI) -> None:
    try:
        from src.agents.generic import start_generic_agent

        agent = start_generic_agent()
        app.state.generic_agent = agent
        if agent is not None:
            logger.info("Generic maintenance agent started: %s", agent.status())
    except Exception:
        logger.exception("Failed to start generic maintenance agent")


async def _shutdown_generic_agent(app: FastAPI) -> None:
    try:
        from src.agents.generic import stop_generic_agent

        stop_generic_agent()
        app.state.generic_agent = None
        logger.info("Generic maintenance agent stopped")
    except Exception:
        logger.exception("Failed to stop generic maintenance agent")


def _recover_orphaned_task_workspaces() -> None:
    try:
        import asyncio as _startup_asyncio

        from src.gateway.routers.task_workspaces import _merge_workspace_metadata
        from src.storage.workflow import TaskWorkflowModule, recoverable_orphaned_workspaces, safe_auto_execute_workspace

        orphaned = recoverable_orphaned_workspaces()
        if orphaned:
            from src.storage.workflow.durable_execution import IdempotentRunner, make_idempotency_key

            global _ORPHAN_RECOVERY_RUNNER
            if _ORPHAN_RECOVERY_RUNNER is None:
                _ORPHAN_RECOVERY_RUNNER = IdempotentRunner()
            runner = _ORPHAN_RECOVERY_RUNNER

            logger.info(
                "Recovering %d orphaned 'running' task workspace(s) on startup: %s",
                len(orphaned),
                [ws.task_id for ws in orphaned],
            )

            def _schedule_recovery(ws: object) -> str:
                _startup_asyncio.create_task(
                    safe_auto_execute_workspace(
                        ws,
                        merge_workspace_metadata=_merge_workspace_metadata,
                        workflow_module_factory=TaskWorkflowModule,
                    )
                )
                return ws.task_id

            skipped = 0
            for ws in orphaned:
                key = make_idempotency_key("recover_orphan_workspace", ws.task_id)
                if runner.store.get(key) is not None:
                    skipped += 1
                # at-most-once: a repeat/concurrent sweep replays instead of re-dispatching
                runner.run(key, lambda ws=ws: _schedule_recovery(ws), name="recover_orphan_workspace")
            if skipped:
                logger.info(
                    "Orphan recovery idempotency guard skipped %d already-recovered workspace(s)",
                    skipped,
                )
        else:
            logger.info("No orphaned task workspaces to recover on startup.")
    except Exception:
        logger.exception("Failed to recover orphaned task workspaces on startup")


async def _shutdown_channel_service() -> None:
    try:
        from src.gateway.channels.service import stop_channel_service

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


async def _sweep_orphaned_langgraph_runs(app: FastAPI) -> None:
    """Cancel ghost LangGraph runs from prior process; start periodic sweeper."""
    try:
        journal_ok = await init_run_journal()
        if journal_ok:
            flipped = await mark_orphans_on_startup()
            logger.info("Harness run journal initialised; orphaned_at_startup=%d", flipped)
    except Exception:
        logger.exception("Harness run journal init failed")
    try:
        report = await sweep_orphaned_runs_once()
        logger.info("Harness orphan-run startup sweep: %s", report)
    except Exception:
        logger.exception("Harness orphan-run startup sweep failed")
    try:
        start_orphan_run_sweeper_task(app)
    except Exception:
        logger.exception("Harness orphan-run sweeper task failed to start")


async def _shutdown_orphan_run_sweeper(app: FastAPI) -> None:
    try:
        await stop_orphan_run_sweeper_task(app)
    except Exception:
        logger.exception("Harness orphan-run sweeper shutdown failed")
    try:
        await shutdown_run_journal()
    except Exception:
        logger.exception("Harness run journal shutdown failed")



async def _warm_embedding_service_async() -> None:
    """Pre-warm the sentence-transformers model at startup to avoid first-call latency."""
    import asyncio

    try:
        from src.models.embedding_service import get_embedding_service

        await asyncio.to_thread(lambda: get_embedding_service().backend)
        logger.info("EmbeddingService warm-up complete (model loaded into memory)")
    except Exception:
        logger.warning("EmbeddingService warm-up failed; model will load on first use", exc_info=True)

@asynccontextmanager
async def gateway_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    config = _initialize_configuration()
    _repair_runtime_permissions(app)
    _initialize_runtime_config(app)
    _initialize_system_guard(app)
    _initialize_service_bus(app, config)
    await _start_channel_service()
    _recover_orphaned_task_workspaces()
    await _sweep_orphaned_langgraph_runs(app)
    _register_reflection_hooks()
    _start_memory_cleanup_scheduler()
    _start_oom_guard(app)
    await start_dispatcher_task(app)
    _start_runtime_maintenance_scheduler(app)
    _start_generic_agent(app)
    await _warm_embedding_service_async()
    yield
    await _shutdown_generic_agent(app)
    await stop_dispatcher_task(app)
    await _shutdown_oom_guard(app)
    await _shutdown_orphan_run_sweeper(app)
    await _shutdown_runtime_maintenance_scheduler(app)
    await _shutdown_channel_service()
    _shutdown_system_guard(app)
    logger.info("Shutting down API Gateway")
