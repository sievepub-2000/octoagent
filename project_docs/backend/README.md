# OctoAgent Backend

OctoAgent is a LangGraph-based AI super agent with sandbox execution, persistent memory, runtime guardrails, and extensible tool integration. The backend enables AI agents to execute code, browse the web, manage files, delegate tasks to subagents, and retain context across conversations in isolated, per-thread environments.

---

## Architecture

```
                        ┌──────────────────────────────────────┐
                        │         Nginx (Port 19880)           │
                        │      Unified reverse proxy           │
                        └───────┬──────────────────┬───────────┘
                                │                  │
              /api/langgraph/*  │                  │  /api/* (other)
                                ▼                  ▼
               ┌────────────────────┐  ┌────────────────────────┐
               │ LangGraph Server   │  │  Gateway API (19882)   │
               │    (Port 19884)    │  │   FastAPI REST         │
               │                    │  │                        │
               │ ┌────────────────┐ │  │ Models, MCP, Skills,   │
               │ │  Lead Agent    │ │  │ Memory, Uploads,       │
               │ │  ┌──────────┐  │ │  │ Artifacts              │
               │ │  │Middleware│  │ │  └────────────────────────┘
               │ │  │  Chain   │  │ │
               │ │  └──────────┘  │ │
               │ │  ┌──────────┐  │ │
               │ │  │  Tools   │  │ │
               │ │  └──────────┘  │ │
               │ │  ┌──────────┐  │ │
               │ │  │Subagents │  │ │
               │ │  └──────────┘  │ │
               │ └────────────────┘ │
               └────────────────────┘
```

**Request Routing** (via Nginx):
- `/api/langgraph/*` → LangGraph Server - agent interactions, threads, streaming
- `/api/*` (other) → Gateway API - models, MCP, skills, memory, artifacts, uploads
- `/` (non-API) → Frontend - Next.js web interface

---

## Core Components

### Lead Agent

The single LangGraph agent (`lead_agent`) is the runtime entry point, created via `make_lead_agent(config)`. It combines:

- **Dynamic model selection** with thinking and vision support
- **Middleware chain** for cross-cutting concerns (11 middlewares)
- **Tool system** with sandbox, MCP, community, and built-in tools
- **Subagent delegation** for parallel task execution
- **System prompt** with skills injection, memory context, and working directory guidance

### Middleware Chain

Middlewares execute in strict order, each handling a specific concern:

| # | Middleware | Purpose |
|---|-----------|---------|
| 1 | **ThreadDataMiddleware** | Creates per-thread isolated directories (workspace, uploads, outputs) |
| 2 | **UploadsMiddleware** | Injects newly uploaded files into conversation context |
| 3 | **SandboxMiddleware** | Acquires sandbox environment for code execution |
| 4 | **ContinuationMiddleware** | Restores workflow/thread continuation state across resumed threads |
| 5 | **SummarizationMiddleware** | Reduces context when approaching token limits (optional) |
| 6 | **TodoListMiddleware** | Tracks multi-step tasks in plan mode (optional) |
| 7 | **TitleMiddleware** | Auto-generates conversation titles after first exchange |
| 8 | **MemoryMiddleware** | Queues conversations for async memory extraction |
| 9 | **RuntimeStateMiddleware** | Persists workflow/runtime state used by inspector and continuation flows |
| 10 | **ViewImageMiddleware** | Injects image data for vision-capable models (conditional) |
| 11 | **ClarificationMiddleware** | Intercepts clarification requests and interrupts execution (must be last) |

### Sandbox System

Per-thread isolated execution with virtual path translation:

- **Abstract interface**: `execute_command`, `read_file`, `write_file`, `list_dir`
- **Providers**: `LocalSandboxProvider` (filesystem) and `AioSandboxProvider` (Docker, in community/)
- **Virtual paths**: `/mnt/user-data/{workspace,uploads,outputs}` → thread-specific physical directories
- **Skills path**: `/mnt/skills` → `octoagent/skills/` directory
- **Skills loading**: Recursively discovers nested `SKILL.md` files under `skills/{public,custom}` and preserves nested container paths
- **Tools**: `bash`, `ls`, `read_file`, `write_file`, `str_replace`

### Subagent System

Delegated task execution with concurrent job control:

- **Built-in agents**: `general-purpose` and other runtime-registered subagent descriptors
- **Runtime model**: centralized delegated-job service with policy, catalog, store, and canonical lifecycle states
- **Execution**: queued job admission, status tracking, timeout handling, rejection semantics, and runtime snapshots
- **Flow**: an agent or workflow entrypoint submits a delegated job through the shared subagent runtime service

### Memory System

LLM-powered persistent context retention across conversations:

- **Automatic extraction**: Analyzes conversations for user context, facts, and preferences
- **Structured storage**: User context (work, personal, top-of-mind), history, and confidence-scored facts
- **Debounced updates**: Batches updates to minimize LLM calls (configurable wait time)
- **System prompt injection**: Top facts + context injected into agent prompts
- **Storage**: JSON file with mtime-based cache invalidation
- **System memory store**: DuckDB-backed `SystemRAGStore` keeps system-generated summaries and operational memory for semantic lookup

Related governance doc:

- `project_docs/backend/SYSTEM_MEMORY_GOVERNANCE.md` — retrieval boundary, retention policy, operator guardrails, and namespace governance for `SystemRAGStore`

### Tool Ecosystem

| Category | Tools |
|----------|-------|
| **Sandbox** | `bash`, `ls`, `read_file`, `write_file`, `str_replace` |
| **Built-in** | `present_files`, `ask_clarification`, `view_image`, `task` (subagent) |
| **Community** | Tavily (web search), Jina AI (web fetch), Firecrawl (scraping), DuckDuckGo (image search) |
| **MCP** | Any Model Context Protocol server (stdio, SSE, HTTP transports) |
| **Skills** | Domain-specific workflows injected via system prompt |

### Gateway API

FastAPI application providing REST endpoints for frontend integration:

| Route | Purpose |
|-------|---------|
| `GET /api/models` | List available LLM models |
| `GET /api/runtime/capabilities` | Runtime guardrails, model fallback, and subagent budgets |
| `GET /api/runtime/system-guard/status` | Latest lifecycle snapshots and retention state |
| `POST /api/runtime/system-guard/repair` | Trigger a manual system-guard repair pass |
| `GET /api/runtime/system-guard/export` | Export signed lifecycle snapshots for offline analysis |
| `GET /api/bootstrap/status` | Embedded bootstrap runtime status |
| `POST /api/bootstrap/install` | Install the embedded bootstrap model |
| `POST /api/bootstrap/guide` | Generate a local onboarding guide |
| `GET /api/integrations/capabilities` | External webhook/API/email/browser ingress capability surface |
| `GET /api/brain/capabilities` | Registered Brain modules and execution-backend surface |
| `POST /api/brain/plan` | Build a Brain Core planning response |
| `GET/PUT /api/mcp/config` | Manage MCP server configurations |
| `GET/PUT /api/skills` | List and manage skills |
| `POST /api/skills/install` | Install skill from `.skill` archive |
| `GET /api/memory` | Retrieve memory data |
| `POST /api/memory/reload` | Force memory reload |
| `GET /api/memory/config` | Memory configuration |
| `GET /api/memory/status` | Combined config + data |
| `GET /api/memory/system/stats` | System memory aggregate stats |
| `POST /api/memory/system/search` | Semantic search over system memory |
| `GET /api/memory/system/list` | Paged system memory listing |
| `POST /api/threads/{id}/uploads` | Upload files (auto-converts PDF/PPT/Excel/Word to Markdown, rejects directory paths) |
| `GET /api/threads/{id}/uploads/list` | List uploaded files |
| `GET /api/threads/{id}/artifacts/{path}` | Serve generated artifacts |
| `GET/POST /api/agents` | Manage custom agents |
| `GET /api/channels` | Inspect IM channel integrations |
| `POST /api/channels/{name}/ingest` | Accept normalized inbound payloads from external bridge connectors |
| `GET /api/threads/{id}/suggestions` | Generate follow-up suggestions |
| `GET /api/system/version` | Report current version and local HEAD |
| `GET /api/system/update/check` | Check GitHub for update availability |
| `POST /api/system/update/apply` | Pull latest code, rebuild, and trigger restart |
| `GET/POST /api/system/update/auto-config` | Read/write auto-update configuration |

### Brain Core

Brain Core is the structured planning layer behind the workflow/orchestrator UI.

- Planner, graph, and contract schemas: `src/brain/*`
- Current analysis modules:
  - `research`
  - `evidence_router`
  - `memory_reasoner`
  - `quant`
- Discovery endpoint:
  - `GET /api/brain/capabilities`
- Planning endpoint:
  - `POST /api/brain/plan`

Brain Core currently emits planning and execution contracts. It does not yet own direct domain execution backends.

## Rowboat Benchmark Integration Direction

Rowboat has been adopted as an external benchmark for the next backend-facing product surface. The relevant takeaway is not “swap runtimes again”, but “make the active runtime easier to inspect, bind, and consume across UI, API, and connectors”.

Backend implications now in scope:

1. `workflow_core` should expose a studio-grade runtime contract, not only file/projection helpers.
2. `agent_core` should own agent session, handoff, pending-tool-call, and runtime summary payloads.
3. Gateway routes should converge toward three clearer families:
  - workspace-internal UI APIs
  - external runtime APIs for SDK/widget callers
  - ingress/channel activation APIs
4. Channel and MCP capability endpoints should become workflow-bindable metadata sources, not only status surfaces.
5. Future Python SDK and widget work should consume explicit contracts rather than internal page-specific payloads.

---

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- API keys for your chosen LLM provider

### Installation

```bash
cd octoagent

# Copy configuration files
cp config.example.yaml config.yaml

# Install backend dependencies
cd backend
uv venv .venv
. .venv/bin/activate
uv pip install -r requirements.txt
```

The canonical Python environment for this repository is `backend/.venv`. Workspace-level scratch virtual environments should not be used for backend development or test execution.

### Configuration

Edit `config.yaml` in the project root:

```yaml
models:
  - name: gpt-4o
    display_name: GPT-4o
    interface_type: openai_compatible
    provider_name: openai
    model: gpt-4o
    api_key: $OPENAI_API_KEY
    supports_thinking: false
    supports_vision: true
```

### Unified Model Interfaces

OctoAgent now prefers an interface-first model configuration shape instead of requiring a raw provider class for every model.

- `interface_type` selects the protocol dialect and default LangChain wrapper.
- `provider_name` documents the actual vendor or gateway and can also be used for alias-based inference.
- `use` remains supported for custom wrappers and legacy configs.

Built-in interface types:

- `openai_compatible` — OpenAI-style chat/completions gateways such as OpenAI, OpenRouter, Groq, Ollama, vLLM, HuggingFace routers, and other compatible local or hosted endpoints.
- `anthropic_messages` — Anthropic Messages style models and compatible gateways.
- `google_genai` — Gemini / Google GenAI integrations.
- `deepseek_reasoner` — DeepSeek-style reasoning gateways and compatible wrappers such as Moonshot/Kimi or Volcengine reasoning models.

Example with automatic class inference:

```yaml
models:
  - name: openrouter-sonnet
    display_name: OpenRouter Claude Sonnet
    interface_type: openai_compatible
    provider_name: openrouter
    model: anthropic/claude-sonnet-4
    base_url: https://openrouter.ai/api/v1
    api_key: $OPENROUTER_API_KEY
    supports_vision: true

  - name: claude-native
    display_name: Claude Native
    interface_type: anthropic_messages
    provider_name: anthropic
    model: claude-sonnet-4-20250514
    api_key: $ANTHROPIC_API_KEY
    supports_thinking: true
    when_thinking_enabled:
      thinking:
        type: enabled
```

If you need a non-standard wrapper, keep using `use` directly:

```yaml
models:
  - name: custom-wrapper
    use: src.models.custom:MyCustomChatModel
    model: custom-model
```

Set your API keys:

```bash
export OPENAI_API_KEY="your-api-key-here"
```

### Running

**Full Application** (from project root):

```bash
make dev  # Starts LangGraph + Gateway + Frontend + Nginx
```

Access at: http://localhost:19880

**Backend Only**:

```bash
cd backend
.venv/bin/python -m langgraph dev --no-browser --allow-blocking --host 127.0.0.1 --port 19884 --no-reload

# separate shell
cd backend
.venv/bin/python -m uvicorn src.gateway.app:app --host 127.0.0.1 --port 19882
```

Direct access: LangGraph at http://localhost:19884, Gateway at http://localhost:19882

---

## Project Structure

```
backend/
├── src/
│   ├── agents/                  # Agent system
│   │   ├── lead_agent/         # Main agent (factory, prompts)
│   │   ├── middlewares/        # 11 middleware components
│   │   ├── memory/             # Memory extraction & storage
│   │   └── thread_state.py    # ThreadState schema
│   ├── gateway/                # FastAPI Gateway API
│   │   ├── app.py             # Application setup
│   │   └── routers/           # REST route modules
│   ├── sandbox/                # Sandbox execution
│   │   ├── local/             # Local filesystem provider
│   │   ├── sandbox.py         # Abstract interface
│   │   ├── tools.py           # bash, ls, read/write/str_replace
│   │   └── middleware.py      # Sandbox lifecycle
│   ├── subagents/              # Subagent delegation
│   │   ├── builtins/          # general-purpose, bash agents
│   │   ├── executor.py        # Background execution engine
│   │   └── registry.py        # Agent registry
│   ├── tools/builtins/         # Built-in tools
│   ├── mcp/                    # MCP protocol integration
│   ├── models/                 # Model factory and fallback wrappers
│   ├── skills/                 # Skill discovery & loading
│   ├── config/                 # Configuration system
│   ├── community/              # Community tools & providers
│   ├── brain/                  # Brain Core planner / graph / policy skeleton
│   ├── bootstrap/              # Embedded bootstrap runtime and semantic store
│   ├── system_guard/           # Lifecycle self-check, repair, export, retention
│   ├── reflection/             # Dynamic module loading
│   └── utils/                  # Utilities
├── docs/                       # Documentation
├── tests/                      # Test suite
├── langgraph.json              # LangGraph server configuration
├── pyproject.toml              # Python dependencies
├── Makefile                    # Development commands
└── Dockerfile                  # Container build
```

---

## Configuration

### Main Configuration (`config.yaml`)

Place in project root. Config values starting with `$` resolve as environment variables.

Scope note:
- `config.example.yaml` is the repository template.
- `config.yaml` is local runtime state and may differ across environments.
- The backend is model-agnostic at the code level: provider selection, fallback chains, and local/remote routing are driven by configuration.
- The embedded bootstrap model is a built-in continuity path, not the default replacement for a user-configured primary model.

Key sections:
- `models` - LLM configurations with class paths, API keys, thinking/vision flags
- `tools` - Tool definitions with module paths and groups
- `tool_groups` - Logical tool groupings
- `sandbox` - Execution environment provider
- `skills` - Skills directory paths
- `title` - Auto-title generation settings
- `summarization` - Context summarization settings
- `subagents` - Subagent system (enabled/disabled)
- `memory` - Memory system settings (enabled, storage, debounce, facts limits)
- `integrations` - External ingress capability planning for webhook, API, email, and browser automation surfaces

Provider note:
- `models[*].use` references provider classes by module path (for example `langchain_openai:ChatOpenAI`).
- If a provider module is missing, OctoAgent returns an actionable error with install guidance (for example `uv add langchain-google-genai`).

### Extensions Configuration (`extensions_config.json`)

MCP servers and skill states in a single file:

```json
{
  "mcpServers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "$GITHUB_TOKEN"}
    },
    "secure-http": {
      "enabled": true,
      "type": "http",
      "url": "https://api.example.com/mcp",
      "oauth": {
        "enabled": true,
        "token_url": "https://auth.example.com/oauth/token",
        "grant_type": "client_credentials",
        "client_id": "$MCP_OAUTH_CLIENT_ID",
        "client_secret": "$MCP_OAUTH_CLIENT_SECRET"
      }
    }
  },
  "skills": {
    "pdf-processing": {"enabled": true}
  }
}
```

### Environment Variables

- `DEER_FLOW_CONFIG_PATH` - Override config.yaml location
- `DEER_FLOW_EXTENSIONS_CONFIG_PATH` - Override extensions_config.json location
- Model API keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, etc.
- Tool API keys: `TAVILY_API_KEY`, `GITHUB_TOKEN`, etc.

---

## Development

### Commands

```bash
make install    # Install dependencies
make dev        # Run LangGraph server (port 2024)
make gateway    # Run Gateway API (port 8001)
make lint       # Run linter (ruff)
make format     # Format code (ruff)
```

### Code Style

- **Linter/Formatter**: `ruff`
- **Line length**: 240 characters
- **Python**: 3.12+ with type hints
- **Quotes**: Double quotes
- **Indentation**: 4 spaces

### Testing

```bash
uv run pytest
```

---

## Technology Stack

- **LangGraph** (1.0.6+) - Agent framework and multi-agent orchestration
- **LangChain** (1.2.3+) - LLM abstractions and tool system
- **FastAPI** (0.115.0+) - Gateway REST API
- **langchain-mcp-adapters** - Model Context Protocol support
- **agent-sandbox** - Sandboxed code execution
- **markitdown** - Multi-format document conversion
- **tavily-python** / **firecrawl-py** - Web search and scraping

---

## Documentation

- [Repository Documentation Index](../docs/README.md)
- [Configuration Guide](docs/CONFIGURATION.md)
- [Architecture Details](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [File Upload](docs/FILE_UPLOAD.md)
- [Path Examples](docs/PATH_EXAMPLES.md)
- [Context Summarization](docs/summarization.md)
- [Plan Mode](docs/plan_mode_usage.md)
- [Setup Guide](docs/SETUP.md)

---

## License

See the [LICENSE](../LICENSE) file in the project root.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.
