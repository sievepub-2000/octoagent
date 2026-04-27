# Portable Python runner: uv preferred, venv fallback
UV_OR_VENV := $(shell command -v uv >/dev/null 2>&1 && echo "uv run" || echo ".venv/bin/python3 -m")

install:
	@if command -v uv >/dev/null 2>&1; then \
		uv sync; \
	elif [ -f .venv/bin/python3 ]; then \
		.venv/bin/python3 -m pip install -r requirements.txt && \
		.venv/bin/python3 -m pip install -e .; \
	else \
		echo "Run '../scripts/bootstrap.sh --backend' first"; exit 1; \
	fi

dev:
	$(UV_OR_VENV) langgraph dev --no-browser --allow-blocking --no-reload --host 127.0.0.1 --port 19884

gateway:
	$(UV_OR_VENV) uvicorn src.gateway.app:app --host 127.0.0.1 --port 19882

test:
	PYTHONPATH=. $(UV_OR_VENV) pytest tests/ -v

lint:
	@if [ -f .venv/bin/ruff ]; then .venv/bin/ruff check .; elif command -v uvx >/dev/null 2>&1; then uvx ruff check .; else echo "ruff not found"; exit 1; fi

format:
	@if [ -f .venv/bin/ruff ]; then .venv/bin/ruff check . --fix && .venv/bin/ruff format .; elif command -v uvx >/dev/null 2>&1; then uvx ruff check . --fix && uvx ruff format .; else echo "ruff not found"; exit 1; fi
