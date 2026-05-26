"""Runtime provider resolution and execution manager."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .contracts import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentRuntimeExecutionSnapshot,
    AgentRuntimeProviderContract,
    AgentRuntimeProviderName,
)
from .providers import LangGraphRuntimeProvider

if TYPE_CHECKING:
    from src.storage.task_workspaces.contracts import TaskWorkspace

logger = logging.getLogger(__name__)

_DEFAULT_PROVIDER: AgentRuntimeProviderName = "langgraph"
_PROVIDER_ALIASES = {
    "crewai": "langgraph",
    "crew_ai": "langgraph",
    "crew-ai": "langgraph",
    "langgraph": "langgraph",
    # Backward-compatible aliases from the removed multi-provider era.
    "openai": "langgraph",
    "openai_agents": "langgraph",
    "openai-agents": "langgraph",
    "unified": "langgraph",
}


class AgentRuntimeManager:
    def __init__(self, providers: dict[AgentRuntimeProviderName, object] | None = None):
        self._providers = providers or {
            "langgraph": LangGraphRuntimeProvider(),
        }
        self._last_execution_snapshots: dict[AgentRuntimeProviderName, AgentRuntimeExecutionSnapshot] = {}

    def resolve_provider_name(
        self,
        *,
        workspace: TaskWorkspace | None = None,
        preferred: str | None = None,
    ) -> AgentRuntimeProviderName:
        candidate = preferred
        if candidate is None and workspace is not None:
            workspace_value = getattr(workspace, "agent_runtime_provider", None)
            if isinstance(workspace_value, str):
                candidate = workspace_value
        if candidate is None and workspace is not None:
            metadata = workspace.metadata if isinstance(workspace.metadata, dict) else {}
            metadata_value = metadata.get("agent_runtime_provider")
            if isinstance(metadata_value, str):
                candidate = metadata_value
        if candidate is None:
            candidate = _DEFAULT_PROVIDER
        normalized = _PROVIDER_ALIASES.get(str(candidate).strip().lower())
        if normalized is None:
            raise RuntimeError(f"Unknown agent runtime provider '{candidate}'. Supported providers: {sorted(self._providers.keys())}.")
        return normalized

    async def execute(
        self,
        request: AgentExecutionRequest,
        *,
        workspace: TaskWorkspace | None = None,
        preferred_provider: str | None = None,
    ) -> AgentExecutionResult:
        # Legacy overrides are normalized to the sole provider.
        effective_preferred = request.agent_runtime_provider_override or preferred_provider
        provider_name = self.resolve_provider_name(workspace=workspace, preferred=effective_preferred)

        provider = self._providers[provider_name]
        result = await provider.execute(request)
        if result.runtime_snapshot is not None:
            self._last_execution_snapshots[provider_name] = result.runtime_snapshot
        return result

    def provider_health(self) -> dict[str, dict[str, object]]:
        """Return availability/status summary for each registered provider."""
        result: dict[str, dict[str, object]] = {}
        for name, provider in self._providers.items():
            available = True
            detail = "ok"
            if hasattr(provider, "is_sdk_available"):
                try:
                    available = provider.is_sdk_available()
                    detail = "ok" if available else "sdk_not_installed"
                except Exception as exc:
                    available = False
                    detail = str(exc)
            sdk_info: dict[str, object] = {}
            if hasattr(provider, "get_sdk_info"):
                try:
                    sdk_info = provider.get_sdk_info()
                except Exception:
                    pass
            result[name] = {"available": available, "detail": detail, "sdk_info": sdk_info}
        return result

    def provider_contracts(self) -> dict[str, AgentRuntimeProviderContract]:
        """Return provider-neutral contract metadata for each registered runtime."""

        contracts: dict[str, AgentRuntimeProviderContract] = {}
        for name, provider in self._providers.items():
            if hasattr(provider, "get_contract"):
                contracts[name] = provider.get_contract()
        return contracts

    def last_execution_snapshots(self) -> dict[str, AgentRuntimeExecutionSnapshot]:
        """Return the most recently observed execution snapshot per provider."""

        return dict(self._last_execution_snapshots)


_runtime_manager: AgentRuntimeManager | None = None


def get_agent_runtime_manager() -> AgentRuntimeManager:
    global _runtime_manager
    if _runtime_manager is None:
        _runtime_manager = AgentRuntimeManager()
    return _runtime_manager


def reset_agent_runtime_manager() -> None:
    global _runtime_manager
    _runtime_manager = None
