# OctoAgent - Unified Development Environment

.PHONY: help config check check-legacy-paths install dev dev-daemon start start-daemon stop clean execution-worker smoke-real smoke-mock smoke-ui smoke-chat-stability smoke-artifact-panel migrate-memory release-precheck operator-release sync-check sync-align sync-references docker-init docker-start docker-stop docker-logs docker-logs-frontend docker-logs-gateway

SMOKE_FRONTEND_URL ?= http://127.0.0.1:$(or $(OCTO_NGINX_PORT),19880)
SMOKE_GATEWAY_URL ?= http://127.0.0.1:$(or $(OCTO_NGINX_PORT),19880)
SMOKE_TIMEOUT_SECONDS ?= 30

help:
	@echo "OctoAgent Development Commands:"
	@echo "  make config          - Generate local config files (aborts if config already exists)"
	@echo "  make check           - Check if all required tools are installed"
	@echo "  make check-legacy-paths - Verify source has no legacy runtime paths"
	@echo "  make install         - Install all dependencies (frontend + backend)"
	@echo "  make setup-sandbox   - Pre-pull sandbox container image (recommended)"
	@echo "  make dev             - Start all services in development mode (with hot-reloading)"
	@echo "  make dev-daemon      - Start all services in background (daemon mode)"
	@echo "  make start-daemon    - Start all services in background (production mode)"
	@echo "  make start           - Start all services in production mode (optimized, no hot-reloading)"
	@echo "  make stop            - Stop all running services"
	@echo "  make execution-worker - Start an independent distributed execution worker"
	@echo "  make smoke-real      - Run real-route WebUI/API smoke checks"
	@echo "  make smoke-mock      - Run mock-route WebUI/API smoke checks"
	@echo "  make smoke-chat-stability - Run chat model/route stability browser smoke"
	@echo "  make smoke-artifact-panel - Run artifact side-panel browser smoke and screenshots"
	@echo "  make release-precheck - Run release precheck (compile/lint/build + smoke)"
	@echo "  make operator-release - Fixed operator release gate (precheck without live smoke)"
	@echo "  make sync-check      - Verify local repo is fully aligned with origin/main"
	@echo "  make sync-align      - Hard-align local repo to origin/main (destructive)"
	@echo "  make sync-references - Sync local third-party reference repos into references/_clones/"
	@echo "  make clean           - Clean up processes and temporary files"
	@echo ""
	@echo "Docker Development Commands:"
	@echo "  make docker-init     - Build the custom k3s image (with pre-cached sandbox image)"
	@echo "  make docker-start    - Start Docker services (mode-aware from config.yaml, localhost:19880)"
	@echo "  make docker-stop     - Stop Docker development services"
	@echo "  make docker-logs     - View Docker development logs"
	@echo "  make docker-logs-frontend - View Docker frontend logs"
	@echo "  make docker-logs-gateway - View Docker gateway logs"

config:
	@if [ -f config.yaml ] || [ -f config.yml ] || [ -f configure.yml ]; then \
		echo "Error: configuration file already exists (config.yaml/config.yml/configure.yml). Aborting."; \
		exit 1; \
	fi
	@cp config.example.yaml config.yaml
	@test -f .env || cp .env.example .env
	@test -f frontend/.env || cp frontend/.env.example frontend/.env

# Check required tools
check:
	@./scripts/check.sh

check-legacy-paths:
	@python3 scripts/check_legacy_paths.py

# Install all dependencies (portable: uv preferred, pip fallback)
install:
	@./scripts/bootstrap.sh

# Install backend only
install-backend:
	@./scripts/bootstrap.sh --backend

# Install frontend only
install-frontend:
	@./scripts/bootstrap.sh --frontend

# Pre-pull sandbox Docker image (optional but recommended)
setup-sandbox:
	@echo "=========================================="
	@echo "  Pre-pulling Sandbox Container Image"
	@echo "=========================================="
	@echo ""
	@IMAGE=$$(grep -A 20 "# sandbox:" config.yaml 2>/dev/null | grep "image:" | awk '{print $$2}' | head -1); \
	if [ -z "$$IMAGE" ]; then \
		IMAGE="enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest"; \
		echo "Using default image: $$IMAGE"; \
	else \
		echo "Using configured image: $$IMAGE"; \
	fi; \
	echo ""; \
	if command -v container >/dev/null 2>&1 && [ "$$(uname)" = "Darwin" ]; then \
		echo "Detected Apple Container on macOS, pulling image..."; \
		container pull "$$IMAGE" || echo "⚠ Apple Container pull failed, will try Docker"; \
	fi; \
	if command -v docker >/dev/null 2>&1; then \
		echo "Pulling image using Docker..."; \
		docker pull "$$IMAGE"; \
		echo ""; \
		echo "✓ Sandbox image pulled successfully"; \
	else \
		echo "✗ Neither Docker nor Apple Container is available"; \
		echo "  Please install Docker: https://docs.docker.com/get-docker/"; \
		exit 1; \
	fi

# Start all services in development mode (with hot-reloading)
dev:
	@./scripts/serve.sh --dev

# Start all services in production mode (with optimizations)
start:
	@./scripts/serve.sh --prod

# Start all services in daemon mode (background)
dev-daemon:
	@./scripts/start-daemon.sh --dev

start-daemon:
	@./scripts/start-daemon.sh --prod

# Stop all services
stop:
	@echo "Stopping all services..."
	@-pkill -f "langgraph dev" 2>/dev/null || true
	@-pkill -f "langgraph_cli dev" 2>/dev/null || true
	@-pkill -f "python -m langgraph_cli" 2>/dev/null || true
	@-pkill -f "uvicorn src.gateway.app:app" 2>/dev/null || true
	@-pkill -f "next dev" 2>/dev/null || true
	@-pkill -f "next start" 2>/dev/null || true
	@-pkill -f "next-server" 2>/dev/null || true
	@-pkill -f "scripts/run_execution_worker.py" 2>/dev/null || true
	@-if command -v fuser >/dev/null 2>&1; then \
		fuser -k "$(or $(OCTO_LANGGRAPH_PORT),19884)/tcp" 2>/dev/null || true; \
		fuser -k "$(or $(OCTO_GATEWAY_PORT),19882)/tcp" 2>/dev/null || true; \
		fuser -k "$(or $(OCTO_FRONTEND_PORT),19886)/tcp" 2>/dev/null || true; \
		fuser -k "$(or $(OCTO_NGINX_PORT),19880)/tcp" 2>/dev/null || true; \
	fi
	@-if [ -f $(PWD)/tmp/nginx.local.conf ]; then nginx -c $(PWD)/tmp/nginx.local.conf -p $(PWD) -s quit 2>/dev/null || true; else nginx -c $(PWD)/docker/nginx/nginx.local.conf -p $(PWD) -s quit 2>/dev/null || true; fi
	@sleep 1
	@-pkill -9 nginx 2>/dev/null || true
	@echo "Cleaning up sandbox containers..."
	@-./scripts/cleanup-containers.sh octoagent-sandbox 2>/dev/null || true
	@echo "✓ All services stopped"

# Clean up
clean: stop
	@echo "Cleaning up..."
	@-rm -rf backend/.octoagent 2>/dev/null || true
	@-rm -rf workspace/.octoagent 2>/dev/null || true
	@-rm -rf backend/.langgraph_api 2>/dev/null || true
	@-rm -rf logs/*.log 2>/dev/null || true
	@echo "✓ Cleanup complete"

execution-worker:
	@cd backend && .venv/bin/python scripts/run_execution_worker.py \
		--host $${OCTO_EXECUTION_WORKER_HOST:-127.0.0.1} \
		--port $${OCTO_EXECUTION_WORKER_PORT:-19982} \
		--node-id $${OCTO_EXECUTION_WORKER_NODE_ID:-worker-local} \
		--token "$${OCTO_EXECUTION_WORKER_TOKEN:-}" \
		--capacity $${OCTO_EXECUTION_WORKER_CAPACITY:-4}

smoke-real:
	@cd backend && .venv/bin/python scripts/run_webui_smoke.py \
		--frontend-url $(SMOKE_FRONTEND_URL) \
		--gateway-url $(SMOKE_GATEWAY_URL) \
		--timeout-seconds $(SMOKE_TIMEOUT_SECONDS)

smoke-mock:
	@cd backend && .venv/bin/python scripts/run_webui_smoke.py \
		--mock \
		--frontend-url http://127.0.0.1:$(or $(OCTO_FRONTEND_PORT),19886) \
		--gateway-url http://127.0.0.1:$(or $(OCTO_GATEWAY_PORT),19882) \
		--timeout-seconds $(SMOKE_TIMEOUT_SECONDS)

smoke-ui:
	@node frontend/scripts/admin_smoke_2026-04-23.cjs

smoke-chat-stability:
	@node frontend/scripts/chat-stability-smoke.cjs $(SMOKE_FRONTEND_URL)

smoke-artifact-panel:
	@node frontend/scripts/chat-artifact-panel-smoke.cjs $(SMOKE_FRONTEND_URL)

migrate-memory:
	@cd backend && .venv/bin/python scripts/migrate_memory_schema.py $(ARGS)

release-precheck:
	@cd backend && .venv/bin/python scripts/run_release_precheck.py \
		--frontend-url $(SMOKE_FRONTEND_URL) \
		--gateway-url $(SMOKE_GATEWAY_URL) \
		--timeout-seconds $(SMOKE_TIMEOUT_SECONDS)

operator-release:
	@cd backend && .venv/bin/python scripts/run_release_precheck.py --skip-smoke

sync-check:
	@./scripts/git-sync.sh check main

sync-align:
	@./scripts/git-sync.sh align main

sync-references:
	@./scripts/sync-reference-repos.sh

# ==========================================
# Docker Development Commands
# ==========================================

# Initialize Docker containers and install dependencies
docker-init:
	@./scripts/docker.sh init

# Start Docker development environment
docker-start:
	@./scripts/docker.sh start

# Stop Docker development environment
docker-stop:
	@./scripts/docker.sh stop

# View Docker development logs
docker-logs:
	@./scripts/docker.sh logs

# View Docker development logs
docker-logs-frontend:
	@./scripts/docker.sh logs --frontend
docker-logs-gateway:
	@./scripts/docker.sh logs --gateway
