# System Tools and MCP Hardening - 2026-05-28

## Runtime

- OctoAgent local service uses the single systemd entry `octoagent-local.service`.
- WebUI is served at `http://192.168.110.2:19800`; gateway health is `http://127.0.0.1:19802/health`; LangGraph docs are `http://127.0.0.1:19804/docs`.
- Backend Python tooling is installed in `backend/.venv` only. Standalone managed binaries are under `runtime/tools/bin`.

## MCP

Enabled MCP servers:

- `filesystem`: full host filesystem access, system-scoped and guarded by permission mode.
- `postgres`: production PostgreSQL DSN resolved from environment, system-scoped and guarded by permission mode.

Removed unavailable MCP entries:

- `camofox-controlled-browser`: removed because `camofox-mcp` could not be independently proven usable on this host; npm cache remnants were deleted.
- `github`: removed because it required an account token and generic repository operations are covered by dedicated `git_*` tools.
- `peekaboo-vision`: removed because no supported `peekaboo` binary exists on this Linux/aarch64 host.

## Built-in System Tools

The registry now enumerates system-scoped tools in capability discovery while preserving each tool's `permission_scope`. The tool surface includes Docker, SSH, Git, database, security, test, awesome-selfhosted reference, and doctor tools. `semgrep_scan` is intentionally absent because current Semgrep releases conflict with the MCP dependency set; `static_security_scan`, `bandit_scan`, and `trivy_scan` cover the security workflow.

## Awesome Selfhosted SaaS Tool

- `awesome_selfhosted` is a sandbox-scoped built-in reference tool for SaaS development stacks.
- It returns curated self-hosted options for deployment, backend, auth, billing, analytics, observability, support, email, automation, storage, DevOps, and project planning.
- It supports `query`, `category`, and `max_results` filters and does not require network access.

## Dependency Policy

- `mcp==1.25.0` and `langchain-mcp-adapters==0.2.1` remain pinned.
- PostgreSQL checkpointer compatibility is pinned with `langgraph-checkpoint==4.1.1`, `langgraph-checkpoint-postgres==3.1.0`, `psycopg[binary]==3.3.4`, and `psycopg-pool==3.3.1`.
- `orjson>=3.11.9` is required for Scrapling compatibility.
- `pip check` must report `No broken requirements found` before release.

## Verified 2026-05-28

- `octoagent-local.service`: active.
- WebUI `/workspace/chats/new`: HTTP 200 after redirect, title `OctoAgent`.
- Gateway `/health`: HTTP 200.
- LangGraph `/docs`: HTTP 200.
- Registry: 91 built-in tools; 2 of 2 configured MCP servers enabled; `semgrep_scan` absent.
- System mode tool load: 104 tools including 13 MCP tools.
- Docker daemon: enabled and active; `docker_status` exits 0.
- Model temperature: all OctoAgent model cards and local Qwen llama.cpp launcher use `0.85`.
