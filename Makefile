# OctoAgent - Unified Development Environment

.PHONY: help config check install install-service ports cli dev dev-daemon start start-daemon stop clean clean-stale-logs smoke-real soak-smoke soak-baseline-suite soak-monitor smoke-mock smoke-ui migrate-memory release-readiness release-readiness-contract smoke-system-executor-security smoke-operator-module-closure release-precheck operator-release sync-check sync-align sync-references docker-init docker-install docker-prod-start docker-prod-stop docker-prod-logs docker-package docker-start docker-stop docker-logs docker-logs-frontend docker-logs-gateway clean-workspace

SMOKE_FRONTEND_URL ?= http://127.0.0.1:$(or $(OCTO_NGINX_PORT),19800)
SMOKE_GATEWAY_URL ?= http://127.0.0.1:$(or $(OCTO_NGINX_PORT),19800)
SMOKE_TIMEOUT_SECONDS ?= 30
RELEASE_READINESS_MIN_SCORE ?= 95
SOAK_PROFILES ?= 2h,8h,24h
SOAK_SAMPLE_INTERVAL_SECONDS ?= 600
SOAK_ITERATIONS ?= 40
SOAK_REPORT_DIR ?=
SOAK_MONITOR_MANIFEST ?=
SOAK_MONITOR_LOOP ?=

help:
	@echo "OctoAgent Development Commands:"
	@echo "  make config          - Generate local config files (aborts if config already exists)"
	@echo "  make check           - Check if all required tools are installed"
	@echo "  make install         - Install all dependencies (frontend + backend)"
	@echo "  make install-service - Run one-command installer in service mode"
	@echo "  make ports           - Show OctoAgent port map"
	@echo "  make cli             - Install the octoagent CLI symlink"
	@echo "  make setup-sandbox   - Pre-pull sandbox container image (recommended)"
	@echo "  make dev             - Start all services in development mode (with hot-reloading)"
	@echo "  make dev-daemon      - Start all services in background (daemon mode)"
	@echo "  make start-daemon    - Start all services in background (production mode)"
	@echo "  make start           - Start all services in production mode (optimized, no hot-reloading)"
	@echo "  make stop            - Stop all running services"
	@echo "  make clean-stale-logs - Truncate stale local runtime logs"
	@echo "  make smoke-real      - Run real-route WebUI/API smoke checks"
	@echo "  make soak-smoke      - Run short bounded long-running soak smoke"
	@echo "  make soak-baseline-suite - Start 2h/8h/24h soak baselines in background"
	@echo "  make soak-monitor SOAK_MONITOR_MANIFEST=<suite.json> - Check soak jobs"
	@echo "  make smoke-mock      - Run mock-route WebUI/API smoke checks"
	@echo "  make release-readiness - Generate release readiness/audit evidence report"
	@echo "  make release-readiness-contract - Validate release readiness manifest contract"
	@echo "  make smoke-system-executor-security - Validate the root executor auth boundary"
	@echo "  make smoke-operator-module-closure - Validate closure contracts for operator substrate modules"
	@echo "  make release-precheck - Run release precheck (compile/lint/build + smoke)"
	@echo "  make operator-release - Fixed operator release gate (precheck without live smoke)"
	@echo "  make sync-check      - Verify local repo is fully aligned with origin/main"
	@echo "  make sync-align      - Hard-align local repo to origin/main (destructive)"
	@echo "  make sync-references - Sync local third-party reference repos into references/_clones/"
	@echo "  make clean           - Clean up processes and temporary files"
	@echo ""
	@echo "Docker Development Commands:"
	@echo "  make docker-init     - Build the custom k3s image (with pre-cached sandbox image)"
	@echo "  make docker-start    - Start Docker services (mode-aware from config.yaml, localhost:19800)"
	@echo "  make docker-stop     - Stop Docker development services"
	@echo "  make docker-logs     - View Docker development logs"
	@echo "  make docker-logs-frontend - View Docker frontend logs"
	@echo "  make docker-logs-gateway - View Docker gateway logs"

config:
	@if [ -f runtime/config/config.yaml ] || [ -f config.yaml ] || [ -f config.yml ] || [ -f configure.yml ]; then \
		echo "Error: configuration file already exists (runtime/config/config.yaml or config.yaml/config.yml/configure.yml). Aborting."; \
		exit 1; \
	fi
	@mkdir -p runtime/config
	@cp config.example.yaml runtime/config/config.yaml
	@chmod 600 runtime/config/config.yaml
	@test -f .env || cp .env.example .env
	@test -f frontend/.env || cp frontend/.env.example frontend/.env

# Check required tools
check:
	@./scripts/check.sh

# Install all dependencies (portable: uv preferred, pip fallback)
install:
	@./scripts/bootstrap.sh

# Install backend only
install-backend:
	@./scripts/bootstrap.sh --backend

# Install frontend only
install-frontend:
	@./scripts/bootstrap.sh --frontend

install-service:
	@./scripts/install-octoagent.sh --mode service

ports:
	@./scripts/octoagent ports

cli:
	@./scripts/install-octoagent.sh --skip-system-packages --skip-bootstrap

# Pre-pull sandbox Docker image (optional but recommended)
setup-sandbox:
	@echo "=========================================="
	@echo "  Pre-pulling Sandbox Container Image"
	@echo "=========================================="
	@echo ""
	@_CFG=runtime/config/config.yaml; [ -f "$$_CFG" ] || _CFG=config.yaml; \
	IMAGE=$$(grep -A 20 "# sandbox:" "$$_CFG" 2>/dev/null | grep "image:" | awk '{print $$2}' | head -1); \
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
	@./scripts/stop-services.sh

# Clean up
clean: stop
	@echo "Cleaning up..."
	@-rm -rf backend/.octoagent 2>/dev/null || true
	@-rm -rf backend/.langgraph_api 2>/dev/null || true
	@-rm -rf logs/*.log 2>/dev/null || true
	@echo "✓ Cleanup complete"

clean-stale-logs:
	@./scripts/clean-stale-runtime-logs.sh

clean-workspace:
	@./scripts/cleanup-workspace.sh

smoke-real:
	@cd backend && .venv/bin/python scripts/run_webui_smoke.py \
		--frontend-url $(SMOKE_FRONTEND_URL) \
		--gateway-url $(SMOKE_GATEWAY_URL) \
		--timeout-seconds $(SMOKE_TIMEOUT_SECONDS)

soak-smoke:
	@cd backend && .venv/bin/python scripts/run_long_running_soak.py \
		--iterations 40 \
		--duration-seconds 5 \
		--sample-interval-seconds 2 \
		--json

soak-baseline-suite:
	@cd backend && .venv/bin/python scripts/run_soak_baseline_suite.py \
		--profiles $(SOAK_PROFILES) \
		$(if $(SOAK_REPORT_DIR),--report-dir $(SOAK_REPORT_DIR),) \
		--sample-interval-seconds $(SOAK_SAMPLE_INTERVAL_SECONDS) \
		--iterations $(SOAK_ITERATIONS) \
		--background \
		--json

soak-monitor:
	@test -n "$(SOAK_MONITOR_MANIFEST)" || (echo "SOAK_MONITOR_MANIFEST is required" && exit 2)
	@cd backend && .venv/bin/python scripts/run_soak_baseline_suite.py \
		--monitor-manifest $(SOAK_MONITOR_MANIFEST) \
		$(if $(SOAK_MONITOR_LOOP),--monitor-loop,) \
		--monitor-interval-seconds $(SOAK_SAMPLE_INTERVAL_SECONDS) \
		--json

smoke-mock:
	@cd backend && .venv/bin/python scripts/run_webui_smoke.py \
		--mock \
		--frontend-url http://127.0.0.1:$(or $(OCTO_FRONTEND_PORT),19806) \
		--gateway-url http://127.0.0.1:$(or $(OCTO_GATEWAY_PORT),19802) \
		--timeout-seconds $(SMOKE_TIMEOUT_SECONDS)

smoke-ui:
	@node frontend/scripts/admin_smoke_2026-04-23.cjs

migrate-memory:
	@cd backend && .venv/bin/python scripts/migrate_memory_schema.py $(ARGS)

migrate-run:
	@cd backend && .venv/bin/python -c "from scripts.migrations.runner import run_migrations; print('Migration runner ready. Pass cursor via application code.')"

migrate-list:
	@cd backend && .venv/bin/python -c "from scripts.migrations.runner import list_migrations; list_migrations()"

migrate-rollback MIGRATION_ID=.:
	@cd backend && .venv/bin/python -c "from scripts.migrations.runner import rollback_migration; print('Rollback target:', "$(MIGRATION_ID)")" 

release-readiness:
	@cd backend && .venv/bin/python scripts/run_release_readiness.py \
		--run-doctor \
		--min-score $(RELEASE_READINESS_MIN_SCORE)

release-readiness-contract:
	@cd backend && .venv/bin/python scripts/run_release_readiness_contract_smoke.py

smoke-system-executor-security:
	@cd backend && .venv/bin/python -m pytest -q tests/system_executor/test_app.py

smoke-operator-module-closure:
	@backend/.venv/bin/python scripts/verify-module-lifecycles.py \
		--base-url $(SMOKE_GATEWAY_URL) \
		--env-file .env.docker

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

# Topology guards (Phase 0 + Phase 7 follow-up)
check-topology-freeze:
	@python3 scripts/check_topology_freeze.py

check-import-boundaries:
	@cd backend && PYTHONPATH=$$PWD .venv/bin/lint-imports --config ../.importlinter

check-topology: check-topology-freeze check-import-boundaries


docker-install:
	@./scripts/install-docker.sh --prefix "$$(pwd)"

docker-prod-start:
	@docker compose --env-file .env.docker -f compose.yaml up -d --build --remove-orphans

docker-prod-stop:
	@docker compose --env-file .env.docker -f compose.yaml down

docker-prod-logs:
	@docker compose --env-file .env.docker -f compose.yaml logs -f nginx gateway langgraph frontend

docker-package:
	@./scripts/package-docker.sh
