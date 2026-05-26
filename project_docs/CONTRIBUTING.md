# Contributing to OctoAgent

Thank you for your interest in contributing to OctoAgent. This guide explains the current development environment and workflow.

## Development Environment Setup

We offer two development environments. **Docker is recommended** for the most consistent and hassle-free experience.

For the current default local port map, see [PORTS.md](/home/sieve-pub/public-workspace/octoagent/project_docs/docs/PORTS.md).

### Option 1: Docker Development (Recommended)

Docker provides a consistent, isolated environment with all dependencies pre-configured. No need to install Node.js, Python, or nginx on your local machine.

#### Prerequisites

- Docker Desktop or Docker Engine
- pnpm (for caching optimization)

#### Setup Steps

1. **Configure the application**:
   ```bash
   # Copy example configuration
   cp config.example.yaml config.yaml

   # Set your API keys
   export OPENAI_API_KEY="your-key-here"
   # or edit config.yaml directly
   ```

2. **Initialize Docker environment** (first time only):
   ```bash
   make docker-init
   ```
   This will:
   - Build Docker images
   - Install frontend dependencies (pnpm)
   - Install backend dependencies (uv)
   - Share pnpm cache with host for faster builds

3. **Start development services**:
   ```bash
   make docker-start
   ```
   `make docker-start` reads `config.yaml` and starts `provisioner` only for provisioner/Kubernetes sandbox mode.

   All services will start with hot-reload enabled:
   - Frontend changes are automatically reloaded
   - Backend changes trigger automatic restart
   - LangGraph server supports hot-reload

4. **Access the application**:
   - Web Interface: http://localhost:19800
   - API Gateway: http://localhost:19800/api/*
   - LangGraph: http://localhost:19800/api/langgraph/*

#### Docker Commands

```bash
# Build the custom k3s image (with pre-cached sandbox image)
make docker-init
# Start Docker services (mode-aware, localhost:19800)
make docker-start
# Stop Docker development services
make docker-stop
# View Docker development logs
make docker-logs
# View Docker frontend logs
make docker-logs-frontend
# View Docker gateway logs
make docker-logs-gateway
```

#### Docker Architecture

```
Host Machine
  ↓
Docker Compose (`octoagent-dev`)
  ├→ nginx (port 19800) ← Reverse proxy
  ├→ web (port 19830) ← Frontend with hot-reload
  ├→ api (port 19832) ← Gateway API with hot-reload
   ├→ langgraph (port 19824) ← LangGraph server with hot-reload
   └→ provisioner (optional, port 19808) ← Started only in provisioner/K8s sandbox mode
```

**Benefits of Docker Development**:
- ✅ Consistent environment across different machines
- ✅ No need to install Node.js, Python, or nginx locally
- ✅ Isolated dependencies and services
- ✅ Easy cleanup and reset
- ✅ Hot-reload for all services
- ✅ Production-like environment

### Option 2: Local Development

If you prefer to run services directly on your machine:

#### Prerequisites

Check that you have all required tools installed:

```bash
make check
```

Required tools:
- Node.js 22+
- pnpm
- uv (Python package manager)
- nginx

#### Setup Steps

1. **Configure the application** (same as Docker setup above)

2. **Install dependencies**:
   ```bash
   make install
   ```

3. **Run development server** (starts all services with nginx):
   ```bash
   make dev
   ```

4. **Access the application**:
   - Web Interface: http://localhost:19800
   - All API requests are automatically proxied through nginx

#### Manual Service Control

If you need to start services individually:

1. **Start backend services**:
   ```bash
   # Terminal 1: Start LangGraph Server (port 19824)
   cd backend
   make dev

   # Terminal 2: Start Gateway API (port 19832)
   cd backend
   make gateway

   # Terminal 3: Start Frontend (port 19830)
   cd frontend
   pnpm dev
   ```

2. **Start nginx**:
   ```bash
   make nginx
   # or directly: nginx -c $(pwd)/docker/nginx/nginx.local.conf -g 'daemon off;'
   ```

3. **Access the application**:
   - Web Interface: http://localhost:19800

#### Nginx Configuration

The nginx configuration provides:
- Unified entry point on port 19800
- Routes `/api/langgraph/*` to LangGraph Server (19824)
- Routes other `/api/*` endpoints to Gateway API (19832)
- Routes non-API requests to Frontend (19830)
- Centralized CORS handling
- SSE/streaming support for real-time agent responses
- Optimized timeouts for long-running operations

## Project Structure

```
octoagent/
├── config.example.yaml      # Configuration template
├── extensions_config.example.json  # MCP and Skills configuration template
├── Makefile                 # Build and development commands
├── scripts/
│   └── docker.sh           # Docker management script
├── docker/
│   ├── docker-compose-dev.yaml  # Docker Compose configuration
│   └── nginx/
│       ├── nginx.conf      # Nginx config for Docker
│       └── nginx.local.conf # Nginx config for local dev
├── backend/                 # Backend application
│   ├── src/
│   │   ├── gateway/        # Gateway API (port 19832)
│   │   ├── agents/         # LangGraph agents (port 19824)
│   │   ├── mcp/            # Model Context Protocol integration
│   │   ├── skills/         # Skills system
│   │   └── sandbox/        # Sandbox execution
│   ├── docs/               # Backend documentation
│   └── Makefile            # Backend commands
├── frontend/               # Frontend application
│   └── Makefile            # Frontend commands
└── skills/                 # Agent skills
    ├── public/             # Public skills
    └── custom/             # Custom skills
```

## Architecture

```
Browser
  ↓
Nginx (port 19800) ← Unified entry point
  ├→ Frontend (port 19830) ← / (non-API requests)
  ├→ Gateway API (port 19832) ← /api/models, /api/mcp, /api/skills, /api/threads/*/artifacts
  └→ LangGraph Server (port 19824) ← /api/langgraph/* (agent interactions)
```

## Development Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** with hot-reload enabled

3. **Verify your changes** with lint, compile, build, and smoke checks

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: description of your changes"
   ```

5. **Push and create a Pull Request**:
   ```bash
   git push origin feature/your-feature-name
   ```

## Verification

```bash
# Backend source verification
cd backend
make test

# Frontend source verification
cd frontend
pnpm lint
pnpm typecheck
```

### PR Gates

Source test suites were removed by operator request on 2026-04-30. Pull requests now rely on repository hygiene, backend lint/compile, frontend lint/typecheck/build, release precheck, and bounded runtime soak smoke gates.

## Code Style

- **Backend (Python)**: We use `ruff` for linting and formatting
- **Frontend (TypeScript)**: We use ESLint and Prettier

## Documentation

- [Configuration Guide](backend/docs/CONFIGURATION.md) - Setup and configuration
- [Architecture Overview](backend/CLAUDE.md) - Technical architecture
- [MCP Setup Guide](MCP_SETUP.md) - Model Context Protocol configuration

## Need Help?

- Check the current repository issue tracker before opening a duplicate report
- Read the [Documentation](backend/docs/)
- Ask questions in the current repository discussion space

## License

By contributing to OctoAgent, you agree that your contributions will be licensed under the [MIT License](./LICENSE).
