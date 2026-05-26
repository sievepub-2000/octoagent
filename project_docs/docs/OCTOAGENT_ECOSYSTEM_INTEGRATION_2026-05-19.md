# OctoAgent Ecosystem Integration Report - 2026-05-19

## Summary

OctoAgent now includes the selected S/A ecosystem projects as first-class built-in capabilities and adds the requested B-class system plugins for `Lumiwealth/lumibot` and `helloianneo/ian-handdrawn-ppt`.

The integration is intentionally layered:

- Skills under `.agents/skills/` provide agent-readable workflows.
- Built-in plugin manifests expose capabilities through `/api/plugins`, the unified capability registry, and `get_plugin_command`.
- `integrated_project_catalog` and `integrated_workflow_run` are real built-in tools that let the lead agent select a project workflow and obtain concrete tool-call sequencing.
- Task-workspace agent execution now has a deterministic integrated-workflow fast path for installed ecosystem workflows. It calls `integrated_project_catalog`, `get_plugin_command`, `load_skill`, and `integrated_workflow_run` through the real tool layer, avoiding misrouting these requests into generic web research fallback.
- Optional MCP templates are registered but disabled by default when the upstream runtime is platform-specific or not installed.

## Integrated S/A Projects

| Project | Repo | Mode |
|---|---|---|
| Agent Rules Books | `ciembor/agent-rules-books` | skill + plugin |
| Mirage VFS | `strukto-ai/mirage` | system-tool concept + plugin + MCP template |
| Peekaboo | `openclaw/Peekaboo` | skill + plugin + MCP template |
| Fireworks Tech Graph | `yizhiyanhua-ai/fireworks-tech-graph` | skill + plugin + workflow tool |
| Beautiful HTML Templates | `zarazhangrui/beautiful-html-templates` | skill + plugin |
| Goalbuddy | `tolibear/goalbuddy` | skill + plugin |
| Photo Agents | `jmerelnyc/Photo-agents` | skill + plugin |
| Lightseek SMG | `lightseekorg/smg` | gateway workflow plugin |
| TokenSpeed | `lightseekorg/tokenspeed` | benchmark workflow plugin |
| WITR | `pranshuparmar/witr` | runtime diagnosis skill + tool workflow |
| Cheat On Content | `XBuilderLAB/cheat-on-content` | content experiment skill + plugin |
| CloakBrowser | `CloakHQ/CloakBrowser` | controlled browser automation plugin, policy gated |

## Requested B-Class System Plugins

| Project | Repo | Integration |
|---|---|---|
| Lumibot | `Lumiwealth/lumibot` | `lumibot-research-strategy` plugin and `integrated_workflow_run` workflow. Research/paper-trading only; live trading is blocked by default. |
| Ian Handdrawn PPT | `helloianneo/ian-handdrawn-ppt` | `ian-handdrawn-ppt` plugin and skill for Chinese hand-drawn technical image deck planning. |

## Agent Workflow Contract

The lead agent can now follow this strict flow:

1. Call `integrated_project_catalog` or `list_capabilities` to discover installed skills/plugins/MCP templates.
2. Call `get_plugin_command` for the selected plugin command.
3. Call `load_skill` when the plugin maps to a skill pack.
4. Call `integrated_workflow_run` with the workflow ID to produce the concrete tool sequence, expected artifacts, and quality gates.
5. Execute the resulting workflow and review artifacts before side effects.

For explicit integrated workflow requests, the task-workspace executor resolves the workflow ID and executes the four-tool chain in a worker thread. This keeps synchronous skill/plugin file loading out of the ASGI event loop and prevents the `load_skill` cache-empty async path from returning a false negative.

## Verification Results

Final verification on 2026-05-19 after service restart:

- Backend: `pytest -q` passed, `176 passed in 6.82s`.
- Frontend: `pnpm typecheck` passed.
- Frontend production build: `pnpm build` passed with Next.js 16.2.3.
- API registry: `/api/plugins/capabilities` reported 16 plugins, including `ian-handdrawn-ppt`, `lumibot-research-strategy`, `tokenspeed-model-benchmark`, and `witr-runtime-diagnostics`.
- API skills: `/api/skills` reported 37 enabled skills, including `agent-rules-books`, `goalbuddy`, `ian-handdrawn-ppt`, `tokenspeed-benchmark`, and `witr-runtime-diagnosis`.
- API tools registry: `/api/tools/registry` reported 41 built-in tools and exposed `integrated_project_catalog` plus `integrated_workflow_run`.
- Agent workflow smoke: created a real task workspace and lead agent, then verified the agent output contained `Integrated Workflow Tool Execution` with real evidence for `integrated_project_catalog`, `get_plugin_command`, `load_skill`, and `integrated_workflow_run`. `load_skill` loaded `.agents/skills/ian-handdrawn-ppt/SKILL.md`; web research fallback was not used.
- WebUI smoke: Playwright loaded `/workspace/config/plugins`, `/workspace/config/skills`, `/workspace/config/tools`, and `/reports/OCTOAGENT_ECOSYSTEM_INTEGRATION_2026-05-19.md` through `http://127.0.0.1:19880`. The pages rendered plugin count 16, skills count 37, built-in tools count 41, and no Next.js error overlay or page error appeared.

## Verification Targets

The integration adds tests for:

- plugin registration and command resolution;
- skill discovery and skill loading;
- catalog/workflow tool outputs;
- paper-trading safety for Lumibot;
- hand-drawn PPT blueprint structure;
- task-workspace integrated workflow fast-path resolution and real tool response generation.
