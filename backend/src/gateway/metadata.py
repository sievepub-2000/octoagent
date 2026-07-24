from __future__ import annotations

API_DESCRIPTION = """
## OctoAgent API Gateway

API Gateway for OctoAgent - A LangGraph-based AI agent backend with sandbox execution capabilities.

### Features

- **Models Management**: Query and retrieve available AI models
- **MCP Configuration**: Manage Model Context Protocol (MCP) server configurations
- **Harness Memory**: Automatic Markdown capture with pgvector recall
- **Skills Management**: Query and manage skills and their enabled status
- **Artifacts**: Access thread artifacts and generated files
- **Health Monitoring**: System health check endpoints

### Architecture

LangGraph requests are handled by nginx reverse proxy.
This gateway provides custom endpoints for models, MCP configuration, skills, and artifacts.
"""

OPENAPI_TAGS = [
    {"name": "agent-runtime", "description": "Native LangGraph runtime and PostgreSQL state summary"},
    {"name": "harness", "description": "Capability discovery, permission dispatch, execution, artifacts, and memory"},
    {"name": "models", "description": "Operations for querying available AI models and their configurations"},
    {"name": "mcp", "description": "Manage Model Context Protocol (MCP) server configurations"},
    {"name": "skills", "description": "Manage skills and their configurations"},
    {"name": "artifacts", "description": "Access and download thread artifacts and generated files"},
    {"name": "uploads", "description": "Upload and manage user files for threads"},
    {"name": "agents", "description": "Create and manage custom agents with per-agent config and prompts"},
    {"name": "suggestions", "description": "Generate follow-up question suggestions for conversations"},
    {"name": "channels", "description": "Manage IM channel integrations (Feishu, Slack, Telegram)"},
    {"name": "integrations", "description": "External webhook/API ingress, auth surface, email, and browser automation capability planning"},
    {"name": "health", "description": "Health check and system status endpoints"},
    {"name": "runtime", "description": "Runtime guardrails, model fallback chains, and subagent budget visibility"},
    {"name": "plugins", "description": "Plugin capability registry for executable engineering workflows"},
    {"name": "browser-runtime", "description": "Browser execution capability discovery and session surfaces"},
    {"name": "transcription", "description": "Audio file speech-to-text transcription via Whisper"},
    {"name": "setup", "description": "First-run setup wizard: workspace validation, configuration, and system status"},
    {"name": "tools", "description": "Unified tool capability registry aggregating MCP, skills, plugins, channels, and runtime"},
    {"name": "auth", "description": "Local authentication and session management"},
    {"name": "hooks", "description": "Harness hook configuration"},
    {"name": "monitoring", "description": "Runtime metrics and audit coverage"},
    {"name": "observation", "description": "Execution observations and traces"},
    {"name": "projects", "description": "PostgreSQL-backed project definitions and runtime policy"},
    {"name": "system", "description": "System module status"},
    {"name": "ws-events", "description": "Live WebSocket event stream"},
]
