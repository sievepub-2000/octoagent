from __future__ import annotations

from pathlib import Path


def test_docker_context_excludes_nested_environment_secrets() -> None:
    dockerignore = Path(__file__).resolve().parents[3] / ".dockerignore"
    patterns = {line.strip() for line in dockerignore.read_text(encoding="utf-8").splitlines()}

    assert ".env" in patterns
    assert "**/.env" in patterns
    assert "**/.env.*" in patterns
    assert "!**/.env.example" in patterns
    assert "!**/.env.*.example" in patterns
    assert "backend/runtime" in patterns
    assert "!skills/**/*.md" in patterns
