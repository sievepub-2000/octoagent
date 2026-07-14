from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from src.gateway.router_contract import build_router_tag_report, validate_router_contract, validate_router_tags
from src.gateway.routers import (
    agents,
    artifacts,
    auth,
    bootstrap,
    brain,
    browser_runtime,
    capabilities,
    channels,
    distributed_execution,
    hooks,
    mcp,
    memory,
    metrics,
    models,
    module_status,
    multi_tenant,
    observation,
    optimization_program,
    orchestration,
    plugins,
    projects,
    query_engine,
    rag_config,
    reflection,
    research_runtime,
    runtime,
    runtime_profile,
    self_evolution,
    setup,
    skill_evolution,
    skills,
    software_interfaces,
    suggestions,
    system_execution,
    system_update,
    task_workspaces,
    tools_registry,
    transcription,
    uploads,
    work_bus,
    ws_events,
)

ROUTERS = [
    projects.router,
    auth.router,
    models.router,
    runtime.router,
    runtime_profile.router,
    bootstrap.router,
    brain.router,
    system_execution.router,
    system_update.router,
    module_status.router,
    task_workspaces.router,
    observation.router,
    optimization_program.router,
    research_runtime.router,
    plugins.router,
    capabilities.router,
    browser_runtime.router,
    orchestration.router,
    query_engine.router,
    rag_config.router,
    mcp.router,
    hooks.router,
    memory.router,
    skills.router,
    skill_evolution.router,
    artifacts.router,
    uploads.router,
    agents.router,
    suggestions.router,
    channels.router,
    transcription.router,
    software_interfaces.router,
    setup.router,
    tools_registry.router,
    ws_events.router,
    work_bus.router,
    metrics.router,
    reflection.router,
    self_evolution.router,
    distributed_execution.router,
    multi_tenant.router,
]

ROUTER_CONTRACT = validate_router_contract(ROUTERS)
ROUTER_TAG_REPORT = build_router_tag_report(ROUTERS)

logger = logging.getLogger(__name__)


def register_routers(app: FastAPI) -> None:
    if os.getenv("OCTOAGENT_STRICT_ROUTER_TAGS", "0") == "1":
        validate_router_tags(ROUTERS)
    elif not ROUTER_TAG_REPORT.ok:
        logger.warning("Gateway router tag report: %s", ROUTER_TAG_REPORT)
    for router in ROUTERS:
        app.include_router(router)
