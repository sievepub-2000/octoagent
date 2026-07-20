import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def _read_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_compose_packages_every_required_runtime_module() -> None:
    dockerfile = (ROOT / "docker" / "Dockerfile.backend-prod").read_text(encoding="utf-8")

    assert "COPY backend ./backend" in dockerfile
    assert "COPY skills ./skills" in dockerfile
    assert "COPY tools/hooks ./tools/hooks" in dockerfile
    assert "COPY runtime/catalogs ./runtime/catalogs" in dockerfile
    assert "runtime/tools/mcp/package-lock.json" in dockerfile
    assert "USER octoagent" in dockerfile
    assert "passwd" in dockerfile
    assert "/usr/local/libexec/docker/cli-plugins" in dockerfile
    assert "/usr/sbin" in dockerfile
    assert "--no-create-home" in dockerfile
    assert "--no-audit" in dockerfile
    assert "chown -R" not in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "--no-install-project" in dockerfile
    assert dockerfile.index("COPY backend/pyproject.toml") < dockerfile.index("COPY backend ./backend")
    assert dockerfile.index("npm ci --omit=dev") < dockerfile.index("COPY backend ./backend")
    assert "uv run uvicorn" not in dockerfile
    mcp_package = _read_json("runtime/tools/mcp/package.json")
    assert "mcp-server-kubernetes" not in mcp_package["dependencies"]
    assert mcp_package["overrides"]["@modelcontextprotocol/sdk"] == "^1.25.3"


def test_mutable_settings_are_persistent_and_writable() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    gateway_volumes = compose["services"]["gateway"]["volumes"]

    assert "./runtime/config:/app/runtime/config" in gateway_volumes
    assert "./backend/runtime:/app/backend/runtime" in gateway_volumes
    assert "./skills/custom:/app/skills/custom" in gateway_volumes
    assert "./tmp:/app/tmp" in gateway_volumes
    assert "./runtime/secrets:/app/runtime/secrets" in gateway_volumes
    assert "./runtime/langgraph:/app/backend/.langgraph_api" in gateway_volumes
    assert all(not volume.endswith(":ro") for volume in gateway_volumes if "/app/runtime/config" in volume)


def test_packaged_profile_has_health_checks_and_persistent_databases() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    expected = {"postgres", "redis", "gateway", "langgraph", "frontend", "nginx"}

    assert expected <= compose["services"].keys()
    assert all("healthcheck" in compose["services"][name] for name in expected)
    assert compose["services"]["postgres"]["volumes"] == ["postgres-data:/var/lib/postgresql/data"]
    assert compose["services"]["redis"]["volumes"] == ["redis-data:/data"]
    assert "uv run" not in compose["services"]["gateway"]["command"]
    assert "uv run" not in compose["services"]["langgraph"]["command"]
    assert "/app/backend/.venv/bin/uvicorn" in compose["services"]["gateway"]["command"]
    assert "/app/backend/.venv/bin/langgraph" in compose["services"]["langgraph"]["command"]


def test_all_supported_platform_installers_are_shipped() -> None:
    assert (ROOT / "scripts" / "install-docker.sh").is_file()
    assert (ROOT / "scripts" / "install-docker.ps1").is_file()
    assert (ROOT / "docs" / "docker-install.md").is_file()
    shell_installer = (ROOT / "scripts" / "install-docker.sh").read_text(encoding="utf-8")
    powershell_installer = (ROOT / "scripts" / "install-docker.ps1").read_text(encoding="utf-8")
    assert '"$PREFIX/compose.yaml"' in shell_installer
    assert 'Join-Path $Prefix "compose.yaml"' in powershell_installer
    assert "RandomNumberGenerator]::Create()" in powershell_installer
    assert "RandomNumberGenerator]::Fill" not in powershell_installer
    assert "/var/log/octoagent_errors.log" not in shell_installer
    assert "POSTGRES_PASSWORD=octoagent-change-me" in shell_installer
    assert 'if [ "$host_uid" = "0" ]' in shell_installer
    assert "New-HexSecret" in powershell_installer
    assert "runtime/config/config.yaml" in shell_installer
    assert 'runtime/config/config.yaml' in powershell_installer
    assert 'ensure_env_csv_value "NO_PROXY" "system-executor"' in shell_installer
    assert 'ensure_env_csv_value "no_proxy" "system-executor"' in shell_installer
    assert 'Ensure-EnvCsvValue -Text $envText -Key "NO_PROXY" -Value "system-executor"' in powershell_installer
    assert 'Ensure-EnvCsvValue -Text $envText -Key "no_proxy" -Value "system-executor"' in powershell_installer


def test_runtime_uses_consolidated_tools_hook_root() -> None:
    service = (ROOT / "backend" / "src" / "harness" / "hook_core" / "service.py").read_text(encoding="utf-8")

    assert 'cls._repo_root() / "tools" / "hooks"' in service
    assert 'cls._repo_root() / ".github" / "hooks"' not in service
    assert 'line.startswith("description:")' in service


def test_frontend_image_uses_repository_toolchain_as_non_root() -> None:
    dockerfile = (ROOT / "docker" / "Dockerfile.frontend-prod").read_text(encoding="utf-8")

    assert "pnpm@11.12.0" in dockerfile
    assert "frontend/pnpm-workspace.yaml" in dockerfile
    assert "USER node" in dockerfile
