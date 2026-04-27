# Project Docs Index

## Canonical Project Path

The only active OctoAgent project root on this host is `/home/sieve-pub/public-workspace/octoagent`. Archived or experimental worktree roots are not active project roots.

`project_docs/` is the active documentation home. Historical imported documents and numbered stage reports were consolidated during the P0 cleanup on 2026-04-25.

## Current Source Of Truth

| Document | Purpose |
| --- | --- |
| `docs/PROJECT_STATUS.md` | Current runtime truth, product boundary, stable surfaces, and known closure areas. |
| `docs/PROJECT_PROGRESS.md` | Current progress, completed work, and next delivery steps. |
| `docs/ARCHITECTURE.md` | System architecture, module map, and runtime shape. |
| `docs/MODULE_PRIORITY_REFACTOR_ROADMAP.md` | P0/P1/P2/P3 priority order and module closure strategy. |
| `docs/P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md` | P0 closure, cleanup summary, validation, and repository sync notes. |
| `docs/CHANNEL_BRIDGE_DEPLOYMENT_GUIDE.md` | Bridge contract, deployment steps, platform matrix, and security boundary. |
| `docs/DEFAULT_AGENT_PROMPT_STANDARD.md` | Canonical default agent prompt standard. |
| `docs/PORTS.md` | Port allocation and local runtime endpoints. |
| `backend/README.md` | Backend architecture and API surface. |
| `frontend/README.md` | Frontend routes, structure, and development workflow. |

## Repository Hygiene

- Keep only repository-owned source, scripts, current docs, examples, and deployment assets in version control.
- Keep local-only runtime state out of the repository root, including virtual environments, frontend build output, node modules, logs, editor archives, screenshots, and temporary research outputs.
- Keep `references/README.md` tracked, but treat `references/_clones/` as local-only synchronized study material.
- Use `.env.example`, `config.example.yaml`, and `extensions_config.example.json` as templates; local real config files stay untracked.

## Deprecated Content

The previous `project_docs/imported/`, `project_docs/archive/`, numbered stage reports, duplicate demo outputs, and transient validation reports were removed during cleanup. Use Git history if a deleted historical report is needed for forensic review.
