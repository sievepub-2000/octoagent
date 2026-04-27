from __future__ import annotations

API_DESCRIPTION = """
## OctoAgent API Gateway

API Gateway for OctoAgent - A LangGraph-based AI agent backend with sandbox execution capabilities.

### Features

- **Models Management**: Query and retrieve available AI models
- **MCP Configuration**: Manage Model Context Protocol (MCP) server configurations
- **Memory Management**: Access and manage global memory data for personalized conversations
- **Skills Management**: Query and manage skills and their enabled status
- **Artifacts**: Access thread artifacts and generated files
- **Health Monitoring**: System health check endpoints

### Architecture

LangGraph requests are handled by nginx reverse proxy.
This gateway provides custom endpoints for models, MCP configuration, skills, and artifacts.
"""

OPENAPI_TAGS = [
    {"name": "models", "description": "Operations for querying available AI models and their configurations"},
    {"name": "mcp", "description": "Manage Model Context Protocol (MCP) server configurations"},
    {"name": "memory", "description": "Access and manage global memory data for personalized conversations"},
    {"name": "skills", "description": "Manage skills and their configurations"},
    {"name": "artifacts", "description": "Access and download thread artifacts and generated files"},
    {"name": "uploads", "description": "Upload and manage user files for threads"},
    {"name": "agents", "description": "Create and manage custom agents with per-agent config and prompts"},
    {"name": "suggestions", "description": "Generate follow-up question suggestions for conversations"},
    {"name": "channels", "description": "Manage IM channel integrations (Feishu, Slack, Telegram)"},
    {"name": "integrations", "description": "External webhook/API ingress, auth surface, email, and browser automation capability planning"},
    {"name": "health", "description": "Health check and system status endpoints"},
    {"name": "runtime", "description": "Runtime guardrails, model fallback chains, and subagent budget visibility"},
    {"name": "bootstrap", "description": "Embedded tiny-model bootstrap runtime, onboarding, and semantic store status"},
    {"name": "brain", "description": "Brain Core planning, strategy-fusion graph generation, and validation"},
    {"name": "system-execution", "description": "System-level execution capability discovery and dry-run planning for future desktop-agent support"},
    {"name": "task-workspaces", "description": "Task-scoped workspaces, card graphs, checkpoints, and agent transcript surfaces"},
    {"name": "research-runtime", "description": "Experiment-loop planning surface for bounded research automation"},
    {"name": "plugins", "description": "Plugin capability registry for executable engineering workflows"},
    {"name": "skill-evolution", "description": "Skill evolution engine with quality monitoring and version tracking"},
    {"name": "browser-runtime", "description": "Browser execution capability discovery and session surfaces"},
    {"name": "orchestration", "description": "Task graph compilation, runtime bindings, and live handoff surfaces"},
    {"name": "query-engine", "description": "Session-scoped query execution and handoff-ready runtime surfaces"},
    {"name": "transcription", "description": "Audio file speech-to-text transcription via Whisper"},
    {"name": "setup", "description": "First-run setup wizard: workspace validation, configuration, and system status"},
    {"name": "tools", "description": "Unified tool capability registry aggregating MCP, skills, plugins, channels, and runtime"},
    {"name": "optimization", "description": "Machine-readable roadmap, scorecard, and benchmark targets for refactor and autoresearch loops"},
]
