"""Contracts for the plugin capability plane."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PluginCommand(BaseModel):
    command_id: str
    title: str
    stage: Literal["ideate", "brainstorm", "plan", "work", "review", "compound", "runtime"]
    summary: str


class PluginManifest(BaseModel):
    plugin_id: str
    display_name: str
    version: str
    provider: str = "octoagent"
    description: str
    commands: list[PluginCommand] = Field(default_factory=list)
    installation_targets: list[str] = Field(default_factory=list)
    review_flow: list[str] = Field(default_factory=list)


class PluginRegistryEntry(BaseModel):
    plugin_id: str
    installed: bool = False
    enabled: bool = False
    installed_version: str | None = None
    source: Literal["builtin", "local", "remote"] = "builtin"
    installed_at: str | None = None


class PluginCapability(BaseModel):
    plugin_id: str
    display_name: str
    category: Literal["engineering", "review", "runtime", "integration"]
    execution_mode: Literal["advisory", "tooling", "workflow"]
    manifest: PluginManifest | None = None
    permissions: list[str] = Field(default_factory=list)
    runtime_requirements: list[str] = Field(default_factory=list)
    enabled: bool = True


class PluginCapabilityListResponse(BaseModel):
    plugins: list[PluginCapability] = Field(default_factory=list)


class PluginManifestListResponse(BaseModel):
    manifests: list[PluginManifest] = Field(default_factory=list)


class PluginRegistryResponse(BaseModel):
    entries: list[PluginRegistryEntry] = Field(default_factory=list)


class PluginInstallRequest(BaseModel):
    plugin_id: str
    source: Literal["builtin", "local", "remote"] = "builtin"
    enable_after_install: bool = True


class PluginToggleRequest(BaseModel):
    enabled: bool = True


class PluginRecommendationRequest(BaseModel):
    mode: Literal["single", "branch", "group"] = "single"
    card_kinds: list[str] = Field(default_factory=list)


class PluginRecommendationResponse(BaseModel):
    plugin_ids: list[str] = Field(default_factory=list)
