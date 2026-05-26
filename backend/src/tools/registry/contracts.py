from __future__ import annotations

from pydantic import BaseModel


class ToolRegistryMcpItem(BaseModel):
    name: str
    enabled: bool
    transport: str
    description: str = ""
    permission_scope: str = "sandbox"


class ToolRegistrySkillItem(BaseModel):
    name: str
    enabled: bool
    category: str
    description: str = ""


class ToolRegistryPluginItem(BaseModel):
    plugin_id: str
    display_name: str
    enabled: bool
    category: str


class ToolRegistryChannelItem(BaseModel):
    name: str
    enabled: bool
    description: str = ""


class ToolRegistryRuntime(BaseModel):
    default_model: str | None = None
    total_models: int = 0
    active_subagents: int = 0
    max_concurrent_subagents: int = 0
    max_total_subagent_jobs: int = 0
    retained_subagent_jobs: int = 0


class ToolRegistrySummary(BaseModel):
    mcp_total: int = 0
    mcp_enabled: int = 0
    skills_total: int = 0
    skills_enabled: int = 0
    plugins_total: int = 0
    plugins_enabled: int = 0
    channels_total: int = 0
    channels_enabled: int = 0
    builtin_tools_total: int = 0


class ToolRegistryBuiltinItem(BaseModel):
    name: str
    description: str = ""
    category: str = "builtin"
    permission_scope: str = "sandbox"


class ToolCapabilityRegistryResponse(BaseModel):
    summary: ToolRegistrySummary
    runtime: ToolRegistryRuntime
    mcp: list[ToolRegistryMcpItem] = []
    skills: list[ToolRegistrySkillItem] = []
    plugins: list[ToolRegistryPluginItem] = []
    channels: list[ToolRegistryChannelItem] = []
    builtin_tools: list[ToolRegistryBuiltinItem] = []
