.PHONY: help docker-install docker-build docker-up docker-down docker-restart docker-status docker-logs verify test lint frontend-build release-check clean-artifacts

COMPOSE := docker compose --env-file .env.docker
BASE_URL ?= http://127.0.0.1:19800

help:
	@echo "OctoAgent Docker commands:"
	@echo "  make docker-install  - Run the one-click Docker installer"
	@echo "  make docker-build    - Build production application images"
	@echo "  make docker-up       - Start the five-service production topology"
	@echo "  make docker-down     - Stop the topology without deleting data"
	@echo "  make docker-restart  - Recreate application services from built images"
	@echo "  make docker-status   - Show service and health state"
	@echo "  make docker-logs     - Follow service logs"
	@echo "  make verify          - Run live retained-module lifecycle checks"
	@echo "  make test            - Run the backend test suite"
	@echo "  make lint            - Run backend Ruff"
	@echo "  make frontend-build  - Run the Next.js production build"
	@echo "  make release-check   - Run all local release gates"
	@echo "  make clean-artifacts - Remove unused Docker images/build cache"

docker-install:
	@./scripts/install-docker.sh

docker-build:
	@$(COMPOSE) build app-server frontend

docker-up:
	@$(COMPOSE) up -d --no-build

docker-down:
	@$(COMPOSE) down

docker-restart:
	@$(COMPOSE) up -d --no-build --force-recreate system-executor app-server frontend nginx

docker-status:
	@$(COMPOSE) ps
	@curl -fsS $(BASE_URL)/health
	@echo

docker-logs:
	@$(COMPOSE) logs -f --tail=200

verify:
	@python3 scripts/verify-module-lifecycles.py --base-url $(BASE_URL)

test:
	@cd backend && .venv/bin/python -m pytest -q tests

lint:
	@cd backend && .venv/bin/python -m ruff check src scripts tests

frontend-build:
	@cd frontend && pnpm exec next build

release-check: lint test frontend-build verify
	@cd backend && .venv/bin/python -m compileall -q src scripts
	@cd backend && .venv/bin/python scripts/run_release_readiness_contract_smoke.py

clean-artifacts:
	@docker image prune -f
	@docker builder prune -af
