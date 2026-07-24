from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from src.gateway.router_contract import build_router_tag_report, validate_router_contract, validate_router_tags
from src.gateway.routers import (
    agent_runtime,
    agents,
    artifacts,
    auth,
    browser_runtime,
    channels,
    harness,
    hooks,
    mcp,
    metrics,
    models,
    module_status,
    observation,
    plugins,
    projects,
    runtime,
    runtime_profile,
    setup,
    skills,
    suggestions,
    transcription,
    uploads,
    ws_events,
)

ROUTERS = [
    agent_runtime.router,
    projects.router,
    auth.router,
    models.router,
    runtime.router,
    runtime_profile.router,
    module_status.router,
    observation.router,
    plugins.router,
    browser_runtime.router,
    mcp.router,
    hooks.router,
    harness.router,
    skills.router,
    artifacts.router,
    uploads.router,
    agents.router,
    suggestions.router,
    channels.router,
    transcription.router,
    setup.router,
    ws_events.router,
    metrics.router,
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
