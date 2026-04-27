"""Interface layer service — central facade for querying runtime capabilities.

Aggregates capability snapshots from all runtime modules and provides
a single entry point for the REST API layer.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class InterfaceLayerService:
    """Central facade that aggregates capability info from all runtime modules.

    Provides a unified API surface for:
      - Listing available capabilities across all runtimes
      - Validating contract payloads before dispatch
      - Collecting runtime health snapshots
    """

    def __init__(self) -> None:
        self._registry: dict[str, dict[str, Any]] = {}
        self._validators: dict[str, Any] = {}

    def register_capability(
        self,
        name: str,
        *,
        version: str = "0.1.0",
        description: str = "",
        contract_type: type | None = None,
    ) -> None:
        """Register a runtime capability with the interface layer."""
        self._registry[name] = {
            "name": name,
            "version": version,
            "description": description,
            "has_contract": contract_type is not None,
        }
        if contract_type is not None:
            self._validators[name] = contract_type

    def list_capabilities(self) -> list[dict[str, Any]]:
        """Return all registered capabilities."""
        return list(self._registry.values())

    def get_capability(self, name: str) -> dict[str, Any] | None:
        """Get a single capability by name."""
        return self._registry.get(name)

    def validate_payload(self, capability_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate a payload against the registered contract for a capability.

        Returns ``{"valid": True}`` on success, or ``{"valid": False, "errors": [...]}``
        on failure.
        """
        contract_cls = self._validators.get(capability_name)
        if contract_cls is None:
            return {"valid": True, "note": "no contract registered — passthrough"}

        try:
            # Pydantic BaseModel validation
            if hasattr(contract_cls, "model_validate"):
                contract_cls.model_validate(payload)
            # Dataclass validation (basic)
            elif hasattr(contract_cls, "__dataclass_fields__"):
                contract_cls(**payload)
            return {"valid": True}
        except Exception as exc:
            return {"valid": False, "errors": [str(exc)]}

    def collect_health(self) -> dict[str, Any]:
        """Collect health snapshots from all registered capabilities."""
        snapshots: dict[str, str] = {}
        for name in self._registry:
            snapshots[name] = "registered"
        return {
            "status": "ok",
            "capabilities_count": len(self._registry),
            "capabilities": snapshots,
        }


_service: InterfaceLayerService | None = None


def get_interface_layer_service() -> InterfaceLayerService:
    """Get the singleton InterfaceLayerService instance."""
    global _service
    if _service is None:
        _service = InterfaceLayerService()
        _register_defaults(_service)
    return _service


def _register_defaults(svc: InterfaceLayerService) -> None:
    """Register all known module capabilities."""
    # Browser runtime
    try:
        from src.browser_runtime import BrowserSessionRequest
        svc.register_capability(
            "browser_runtime",
            version="0.3.0",
            description="Browser-based page fetching, action execution, and session management",
            contract_type=BrowserSessionRequest,
        )
    except ImportError:
        pass

    # Research runtime
    try:
        from src.research_runtime import CreateResearchExperimentRequest
        svc.register_capability(
            "research_runtime",
            version="0.3.0",
            description="Bounded auto-research with experiment design and trial execution",
            contract_type=CreateResearchExperimentRequest,
        )
    except ImportError:
        pass

    # Orchestration
    try:
        svc.register_capability(
            "orchestration",
            version="0.3.0",
            description="Task graph compilation and execution with budget policies",
        )
    except ImportError:
        pass

    # Plugins
    try:
        from src.plugins import PluginInstallRequest
        svc.register_capability(
            "plugins",
            version="0.3.0",
            description="Plugin discovery, installation, and lifecycle management",
            contract_type=PluginInstallRequest,
        )
    except ImportError:
        pass

    # Query engine
    try:
        svc.register_capability(
            "query_engine",
            version="0.3.0",
            description="Natural language query execution and session management",
        )
    except ImportError:
        pass

    # Skill evolution
    try:
        svc.register_capability(
            "skill_evolution",
            version="0.3.0",
            description="Post-execution skill analysis, evolution, and quality monitoring",
        )
    except ImportError:
        pass

    # Brain
    try:
        svc.register_capability(
            "brain",
            version="0.3.0",
            description="Multi-module analysis pipeline with planning, policy, and execution",
        )
    except ImportError:
        pass

    # Studio runtime
    try:
        svc.register_capability(
            "studio_runtime",
            version="0.3.0",
            description="Visual workflow compilation and lifecycle management",
        )
    except ImportError:
        pass

    # Session compaction
    try:
        svc.register_capability(
            "session_compaction",
            version="0.3.0",
            description="Context compression with truncate/summarize/hybrid strategies",
        )
    except ImportError:
        pass

    # Channel SDK
    try:
        svc.register_capability(
            "channel_sdk",
            version="0.3.0",
            description="WebSocket event streaming and channel management",
        )
    except ImportError:
        pass

    # Reflection
    try:
        svc.register_capability(
            "reflection",
            version="0.3.0",
            description="Execution observation recording and insight derivation",
        )
    except ImportError:
        pass

    logger.info("Interface layer: %d capabilities registered", len(svc.list_capabilities()))
