from .contracts import (
    PluginCapability,
    PluginCapabilityListResponse,
    PluginCommand,
    PluginInstallRequest,
    PluginManifest,
    PluginManifestListResponse,
    PluginRecommendationRequest,
    PluginRecommendationResponse,
    PluginRegistryEntry,
    PluginRegistryResponse,
    PluginToggleRequest,
)
from .service import get_plugin_service

__all__ = [
    "PluginInstallRequest",
    "PluginCapability",
    "PluginCapabilityListResponse",
    "PluginCommand",
    "PluginManifest",
    "PluginManifestListResponse",
    "PluginRecommendationRequest",
    "PluginRecommendationResponse",
    "PluginRegistryEntry",
    "PluginRegistryResponse",
    "PluginToggleRequest",
    "get_plugin_service",
]
