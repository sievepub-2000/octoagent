"""The two public OctoAgent Modules and their private Interface registry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModuleLayer(str, Enum):
    SERVER = "server"
    CLIENT = "client"
    SHARED = "shared"


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    layer: ModuleLayer
    description: str
    package: str
    dependencies: tuple[str, ...] = ()


# Public architecture. Models, storage, adapters, registries, and protocols are
# Implementations behind these two deep Interfaces, not additional Modules.
MODULE_REGISTRY: dict[str, ModuleInfo] = {
    "agent_runtime": ModuleInfo(
        name="agent_runtime",
        layer=ModuleLayer.SERVER,
        description="Owns model turns, LangGraph state, Project/Task/Run data, and streaming.",
        package="src.agents",
        dependencies=("harness",),
    ),
    "harness": ModuleInfo(
        name="harness",
        layer=ModuleLayer.SERVER,
        description="Owns capability discovery, permission dispatch, execution, traces, artifacts, and memory.",
        package="src.harness",
    ),
}

# Kept for compatibility with the runtime status API. Router files are thin
# Interfaces of the two Modules, not architectural Modules themselves.
CLIENT_ROUTERS = ["agent_runtime", "harness"]
SERVER_ROUTERS = ["agent_runtime", "harness"]


def get_module_info(name: str) -> ModuleInfo | None:
    return MODULE_REGISTRY.get(name)


def get_modules_by_layer(layer: ModuleLayer) -> list[ModuleInfo]:
    return [module for module in MODULE_REGISTRY.values() if module.layer == layer]
