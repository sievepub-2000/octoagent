# One-Line Install And OctoAgent CLI

OctoAgent supports a repository-owned installer and a single `octoagent` operator command. The installer prepares the backend virtual environment, frontend dependencies, runtime directories, default model setup state, optional systemd service, and the CLI symlink.

## One-Line Install

Development/local mode:

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-octoagent.sh | bash -s -- --prefix "$HOME/octoagent" --yes
```

Service mode with automatic start:

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-octoagent.sh | bash -s -- --prefix /home/sieve-pub/public-workspace/octoagent --user sieve-pub --mode service --yes --start
```

Non-interactive automation must pass `--yes` before the installer changes OS packages, installs the `/usr/local/bin/octoagent` symlink, or refreshes systemd:

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-octoagent.sh | bash -s -- --prefix /opt/octoagent --user octoagent --mode service --default-model qwen3.6-35b-a3b-q8-mm-prod --yes --start
```

The installer currently supports automatic OS package installation on apt-based Linux hosts. Other platforms should install Python 3.12+, Node.js 22+, nginx, git, curl, and build-essential first, then rerun with `--skip-system-packages`.

## CLI

After installation, run the whole stack with one command:

```bash
octoagent
```

Useful commands:

```bash
octoagent configure
octoagent configure --default-model qwen3.6-35b-a3b-q8-mm-prod --yes
octoagent ports
octoagent status
octoagent restart
octoagent doctor
```

`octoagent configure` writes `workspace/env/setup.json`. It sets `default_model`, workspace paths, and runtime layout without overwriting an existing `config.yaml`. If `config.yaml` is missing, it is created from `config.example.yaml` first.

## FAISS Runtime Placement

FAISS is an OctoAgent RAG runtime dependency, not a standalone host tool. The Python package is installed in the OctoAgent backend virtual environment at `backend/.venv` so the LangGraph/Gateway process can import it directly. Do not create an extra host-level or tool-local virtual environment for FAISS unless FAISS is later split into an external service.

The reproducible dependency is tracked in:

- `backend/pyproject.toml`
- `backend/uv.lock`
- `backend/requirements.txt`

## Port Map

| Port | Variable | Component | Notes |
| --- | --- | --- | --- |
| 19800 | `OCTO_NGINX_PORT` | nginx ingress | Unified WebUI and API entrypoint |
| 19802 | `OCTO_GATEWAY_PORT` | FastAPI gateway | REST APIs, auth proxy, model/config/tool endpoints |
| 19804 | `OCTO_LANGGRAPH_PORT` | LangGraph runtime | Agent run and stream runtime |
| 19806 | `OCTO_FRONTEND_PORT` | Next.js frontend | Internal frontend target behind nginx |
| 19808 | `OCTO_PROVISIONER_PORT` | Sandbox provisioner | Optional Docker/Kubernetes provisioner mode |
| 19810 | `OCTO_TTYD_PORT` | ttyd terminal | Local terminal bridge when enabled |
| 19820+ | `OCTO_SANDBOX_BASE_PORT` | Sandbox containers | Dynamic per-sandbox allocation base |
| 19812 | `OCTO_EXECUTION_WORKER_PORT` | Execution worker | Optional distributed worker service |
| 19814 | `LISTEN_PORT` | Generic webhook bridge | Optional example bridge listener |
| 19880 / 19882 / 19884 | NapCat / OneBot | QQ channel bridge | Optional QQ/NapCat bridge ports; later communication channels use `19880 + 10*n` blocks |

The source of truth for the core local ports is `scripts/port-layout.sh`; `octoagent ports` renders the active values after environment overrides.
