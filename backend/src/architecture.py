"""OctoAgent Architecture — Server/Client Module Classification.

This module defines the architectural boundary between server-side (core)
and client-side (gateway) modules, providing a unified service registry
for inter-module communication.

Architecture:
    ┌─────────────────────────────────────────────────────┐
    │  CLIENT LAYER (Gateway)                             │
    │  User-facing APIs, config UI, external integrations │
    │                                                     │
    │  Routers: setup, models, agents, skills, mcp,       │
    │           memory, uploads, artifacts, suggestions,   │
    │           channels, integrations, transcription,     │
    │           bootstrap, skill_evolution, plugins        │
    └────────────────────┬────────────────────────────────┘
                         │ ServiceBus (typed interface)
    ┌────────────────────▼────────────────────────────────┐
    │  SERVER LAYER (Core)                                │
    │  Agent execution, reasoning, sandbox, system tools  │
    │                                                     │
    │  Modules: agents, brain, orchestration, sandbox,    │
    │           query_engine, subagents, system_execution, │
    │           system_guard, research_runtime,            │
    │           browser_runtime, session_compaction,       │
    │           task_workspaces, tools                     │
    └─────────────────────────────────────────────────────┘
    ┌─────────────────────────────────────────────────────┐
    │  SHARED LAYER                                       │
    │  Config, models, paths, utils, reflection           │
    └─────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ModuleLayer(str, Enum):
    """Architectural layer classification."""
    SERVER = "server"    # Core processing, agent execution, system tools
    CLIENT = "client"    # Gateway APIs, user config, external integrations
    SHARED = "shared"    # Cross-cutting: config, models, paths, utils


@dataclass(frozen=True)
class ModuleInfo:
    """Metadata about a registered module."""
    name: str
    layer: ModuleLayer
    description: str
    package: str          # e.g. "src.agents"
    dependencies: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Module Registry — canonical classification of all backend modules
# ---------------------------------------------------------------------------

MODULE_REGISTRY: dict[str, ModuleInfo] = {
    # === SERVER LAYER (core processing) ===
    "agents": ModuleInfo(
        name="agents",
        layer=ModuleLayer.SERVER,
        description="Lead agent construction, middleware stack, prompt templates",
        package="src.agents",
        dependencies=("config", "tools", "models", "sandbox"),
    ),
    "brain": ModuleInfo(
        name="brain",
        layer=ModuleLayer.SERVER,
        description="Planning graphs, strategy fusion, validation",
        package="src.brain",
        dependencies=("config", "models"),
    ),
    "orchestration": ModuleInfo(
        name="orchestration",
        layer=ModuleLayer.SERVER,
        description="Task graph compilation, runtime bindings",
        package="src.orchestration",
        dependencies=("config", "agents"),
    ),
    "sandbox": ModuleInfo(
        name="sandbox",
        layer=ModuleLayer.SERVER,
        description="Code execution isolation (local / Docker)",
        package="src.sandbox",
        dependencies=("config",),
    ),
    "query_engine": ModuleInfo(
        name="query_engine",
        layer=ModuleLayer.SERVER,
        description="Session-scoped query execution",
        package="src.query_engine",
        dependencies=("config", "session_compaction"),
    ),
    "subagents": ModuleInfo(
        name="subagents",
        layer=ModuleLayer.SERVER,
        description="Multi-agent runtime, budget management",
        package="src.subagents",
        dependencies=("agents", "config"),
    ),
    "system_execution": ModuleInfo(
        name="system_execution",
        layer=ModuleLayer.SERVER,
        description="Desktop execution planning, OS-level operations",
        package="src.system_execution",
        dependencies=("config",),
    ),
    "system_guard": ModuleInfo(
        name="system_guard",
        layer=ModuleLayer.SERVER,
        description="Lifecycle management, self-repair, vector snapshots",
        package="src.system_guard",
        dependencies=("config",),
    ),
    "research_runtime": ModuleInfo(
        name="research_runtime",
        layer=ModuleLayer.SERVER,
        description="Experiment-loop planning for bounded research",
        package="src.research_runtime",
        dependencies=("config",),
    ),
    "browser_runtime": ModuleInfo(
        name="browser_runtime",
        layer=ModuleLayer.SERVER,
        description="Browser automation capability surface",
        package="src.browser_runtime",
        dependencies=("config",),
    ),
    "session_compaction": ModuleInfo(
        name="session_compaction",
        layer=ModuleLayer.SERVER,
        description="Context window compression (claw-code integration)",
        package="src.session_compaction",
        dependencies=("config",),
    ),
    "task_workspaces": ModuleInfo(
        name="task_workspaces",
        layer=ModuleLayer.SERVER,
        description="Task-scoped workspaces, card graphs, checkpoints",
        package="src.task_workspaces",
        dependencies=("config",),
    ),
    "workflow_core": ModuleInfo(
        name="workflow_core",
        layer=ModuleLayer.SERVER,
        description="Workflow application facade over task workspaces and orchestration",
        package="src.workflow_core",
        dependencies=("config", "task_workspaces", "orchestration"),
    ),
    "agent_core": ModuleInfo(
        name="agent_core",
        layer=ModuleLayer.SERVER,
        description="Agent runtime facade over workflow-bound agent lifecycle operations",
        package="src.agent_core",
        dependencies=("config", "workflow_core", "agents", "subagents"),
    ),
    "tools": ModuleInfo(
        name="tools",
        layer=ModuleLayer.SERVER,
        description="Built-in tools: image, web, document, clarification, task",
        package="src.tools",
        dependencies=("config", "mcp"),
    ),

    # === CLIENT LAYER (gateway / user-facing) ===
    "gateway": ModuleInfo(
        name="gateway",
        layer=ModuleLayer.CLIENT,
        description="FastAPI gateway, CORS, router mounting, health check",
        package="src.gateway",
        dependencies=("config",),
    ),
    "bootstrap": ModuleInfo(
        name="bootstrap",
        layer=ModuleLayer.CLIENT,
        description="Embedded model, onboarding, semantic store",
        package="src.bootstrap",
        dependencies=("config",),
    ),
    "channels": ModuleInfo(
        name="channels",
        layer=ModuleLayer.CLIENT,
        description="IM integrations: Feishu, Slack, Telegram",
        package="src.channels",
        dependencies=("config",),
    ),
    "skill_evolution": ModuleInfo(
        name="skill_evolution",
        layer=ModuleLayer.CLIENT,
        description="Skill evolution engine, quality monitoring (OpenSpace-inspired)",
        package="src.skill_evolution",
        dependencies=("config", "skills"),
    ),
    "plugins": ModuleInfo(
        name="plugins",
        layer=ModuleLayer.CLIENT,
        description="Plugin capability registry",
        package="src.plugins",
        dependencies=("config",),
    ),
    "interface_layer": ModuleInfo(
        name="interface_layer",
        layer=ModuleLayer.CLIENT,
        description="Execution contracts and API interfaces",
        package="src.interface_layer",
        dependencies=("config",),
    ),

    # === SHARED LAYER ===
    "config": ModuleInfo(
        name="config",
        layer=ModuleLayer.SHARED,
        description="App config, paths, embedded model, extensions, memory",
        package="src.config",
    ),
    "models": ModuleInfo(
        name="models",
        layer=ModuleLayer.SHARED,
        description="Model factory, fallback chains, provider adapters",
        package="src.models",
        dependencies=("config",),
    ),
    "skills": ModuleInfo(
        name="skills",
        layer=ModuleLayer.SHARED,
        description="Skill loader, SKILL.md parser",
        package="src.skills",
        dependencies=("config",),
    ),
    "mcp": ModuleInfo(
        name="mcp",
        layer=ModuleLayer.SHARED,
        description="MCP server configs, tool cache",
        package="src.mcp",
        dependencies=("config",),
    ),
    "reflection": ModuleInfo(
        name="reflection",
        layer=ModuleLayer.SHARED,
        description="Dynamic module resolution (resolve_variable)",
        package="src.reflection",
    ),
    "utils": ModuleInfo(
        name="utils",
        layer=ModuleLayer.SHARED,
        description="Shared utilities (token counting, text processing)",
        package="src.utils",
    ),
}


# ---------------------------------------------------------------------------
# Gateway Router Classification
# ---------------------------------------------------------------------------

# Client-facing routers (user interaction, configuration)
CLIENT_ROUTERS = [
    "setup",           # First-run wizard
    "models",          # Model listing & config
    "agents",          # Agent CRUD
    "skills",          # Skill management
    "mcp",             # MCP server config
    "memory",          # Memory access
    "uploads",         # File uploads
    "artifacts",       # File downloads
    "suggestions",     # Follow-up suggestions
    "channels",        # IM integrations
    "integrations",    # External API hooks
    "transcription",   # Audio STT
    "bootstrap",       # Onboarding
    "skill_evolution", # Skill evolution dashboard
    "plugins",         # Plugin registry
]

# Server-internal routers (expose core capabilities to gateway proxy)
SERVER_ROUTERS = [
    "runtime",           # Capability & guardrails
    "brain",             # Planning engine
    "system_execution",  # Desktop exec planning
    "task_workspaces",   # Task management
    "research_runtime",  # Research loops
    "browser_runtime",   # Browser automation
    "orchestration",     # Task graph compilation
    "query_engine",      # Query execution
]


# ---------------------------------------------------------------------------
# ServiceBus — typed interface for cross-layer communication
# ---------------------------------------------------------------------------

@dataclass
class ServiceBus:
    """Unified interface registry for server/client module communication.

    Instead of direct cross-layer imports, modules register and retrieve
    services through this bus, keeping the dependency graph clean.
    """
    _services: dict[str, Any] = field(default_factory=dict)

    def register(self, name: str, service: Any) -> None:
        """Register a service for cross-module access."""
        self._services[name] = service
        logger.debug("ServiceBus: registered %s", name)

    def get(self, name: str) -> Any | None:
        """Retrieve a registered service."""
        return self._services.get(name)

    def require(self, name: str) -> Any:
        """Retrieve a registered service, raising if not found."""
        svc = self._services.get(name)
        if svc is None:
            raise KeyError(f"Service '{name}' not registered in ServiceBus")
        return svc

    @property
    def registered(self) -> list[str]:
        return list(self._services.keys())


# Singleton service bus instance
_bus: ServiceBus | None = None


def get_service_bus() -> ServiceBus:
    """Get the global ServiceBus singleton."""
    global _bus
    if _bus is None:
        _bus = ServiceBus()
    return _bus


def get_module_info(name: str) -> ModuleInfo | None:
    """Look up module metadata by name."""
    return MODULE_REGISTRY.get(name)


def get_modules_by_layer(layer: ModuleLayer) -> list[ModuleInfo]:
    """Return all modules in a given architectural layer."""
    return [m for m in MODULE_REGISTRY.values() if m.layer == layer]
