# OctoAgent System Tool Guide

This file is auto-generated from the current OctoAgent runtime state.
Whenever skills, plugins, MCP servers, or hooks are added, removed, enabled, disabled, or reconfigured, this file must be regenerated immediately.

## System Rules

- Before every specialized tool action, query Tools Hub (`/api/tools/registry` or `list_capabilities`) and use an installed, enabled, callable capability first.
- When several installed capabilities plausibly match, try them in least-privilege order and continue to the next candidate only when the prior result is unusable.
- Search GitHub only after Tools Hub has no suitable capability; install only a reviewed HTTPS GitHub source pinned to a tag/branch under `runtime/system_tools/<tool>`.
- Never run ad-hoc pip/npm installs in the backend environment or user site-packages. Every operator-installed tool needs `manifest.json`, a verification result, and a Tools Hub entry.
- Uninstall through the owning Skills/MCP/Plugins/Managed Tools lifecycle. Confirm the exact root, remove it, refresh this guide, and verify post-delete invisibility.
- If a capability depends on runtime state, check installed/enabled state and activation blockers first.
- Before using a managed capability category, read the relevant section in this file and follow the listed interface contract.
- After any change to skills/plugins/MCP/hooks, regenerate this guide.

## Registry Summary

- Generated at: 2026-07-15T01:28:19.798416+00:00
- Total capabilities: 83
- Enabled capabilities: 73
- Installed capabilities: 83
- Channel: 10 total, 0 enabled
- MCP Servers: 6 total, 6 enabled
- Plugins: 16 total, 16 enabled
- Skills: 51 total, 51 enabled

## Interface Contract

- Skills: load the skill file first, then execute its prescribed workflow.
- Plugins: prefer provided command IDs over recreating the same action manually.
- MCP servers: verify server availability and authentication before using remote tools/resources.
- Hooks: treat them as event-driven integration points; update runtime and repository state together.

## Channel (10)

- Facebook Messenger (channel:facebook_messenger)
  State: installed, disabled
  Description: Bridge-backed Facebook Messenger connector relayed through an external webhook adapter.
  Source: external_bridge
  Provides: channel:facebook_messenger, transport:webhook_bridge, integration:external_bridge, /api/channels/facebook_messenger/ingest
  Requires: config:shared_secret

- Feishu/Lark (channel:feishu)
  State: installed, disabled
  Description: Native Feishu/Lark websocket connector.
  Source: native
  Provides: channel:feishu, transport:websocket, integration:native
  Requires: config:app_id, config:app_secret

- KakaoTalk (channel:kakaotalk)
  State: installed, disabled
  Description: Bridge-backed KakaoTalk connector relayed through an external webhook adapter.
  Source: external_bridge
  Provides: channel:kakaotalk, transport:webhook_bridge, integration:external_bridge, /api/channels/kakaotalk/ingest
  Requires: config:shared_secret

- LINE (channel:line)
  State: installed, disabled
  Description: Bridge-backed LINE connector relayed through an external webhook adapter.
  Source: external_bridge
  Provides: channel:line, transport:webhook_bridge, integration:external_bridge, /api/channels/line/ingest
  Requires: config:shared_secret

- QQ (channel:qq)
  State: installed, disabled
  Description: Bridge-backed QQ connector relayed through an external webhook adapter.
  Source: external_bridge
  Provides: channel:qq, transport:webhook_bridge, integration:external_bridge, /api/channels/qq/ingest
  Requires: config:shared_secret

- Slack (channel:slack)
  State: installed, disabled
  Description: Native Slack connector using Socket Mode.
  Source: native
  Provides: channel:slack, transport:socket_mode, integration:native
  Requires: config:bot_token, config:app_token

- Telegram (channel:telegram)
  State: installed, disabled
  Description: Native Telegram connector using long polling.
  Source: native
  Provides: channel:telegram, transport:long_polling, integration:native
  Requires: config:bot_token

- WeChat (channel:wechat)
  State: installed, disabled
  Description: Bridge-backed WeChat connector relayed through an external webhook adapter.
  Source: external_bridge
  Provides: channel:wechat, transport:webhook_bridge, integration:external_bridge, /api/channels/wechat/ingest
  Requires: config:shared_secret

- WhatsApp (channel:whatsapp)
  State: installed, disabled
  Description: Bridge-backed WhatsApp connector relayed through an external webhook adapter.
  Source: external_bridge
  Provides: channel:whatsapp, transport:webhook_bridge, integration:external_bridge, /api/channels/whatsapp/ingest
  Requires: config:shared_secret

- Zalo (channel:zalo)
  State: installed, disabled
  Description: Bridge-backed Zalo connector relayed through an external webhook adapter.
  Source: external_bridge
  Provides: channel:zalo, transport:webhook_bridge, integration:external_bridge, /api/channels/zalo/ingest
  Requires: config:shared_secret

## MCP Servers (6)

- docker (mcp_server:docker)
  State: installed, enabled
  Description: Docker MCP package connected to the local Docker daemon; includes safe listing/version smoke checks.
  Source: stdio
  Transport: stdio
  Command: /home/sieve-pub/public-workspace/octoagent/runtime/tools/mcp/node_modules/.bin/docker-mcp
  Provides: mcp_server:docker
  Requires: none
  When to use: external systems, hosted tools, or remote resources are required.
  How to use: verify server is enabled, authenticate if required, then call the server's tools/resources instead of ad-hoc HTTP requests.

- docker-compose (mcp_server:docker-compose)
  State: installed, enabled
  Description: Local Docker Compose inspection MCP for version and compose config validation.
  Source: stdio
  Transport: stdio
  Command: /home/sieve-pub/public-workspace/octoagent/backend/.venv/bin/python
  Provides: mcp_server:docker-compose
  Requires: none
  When to use: external systems, hosted tools, or remote resources are required.
  How to use: verify server is enabled, authenticate if required, then call the server's tools/resources instead of ad-hoc HTTP requests.

- filesystem (mcp_server:filesystem)
  State: installed, enabled
  Description: System-scoped filesystem MCP with full host filesystem access; guarded by chat permission mode.
  Source: stdio
  Transport: stdio
  Command: /home/sieve-pub/public-workspace/octoagent/runtime/tools/mcp/node_modules/.bin/mcp-server-filesystem
  Provides: mcp_server:filesystem
  Requires: none
  When to use: external systems, hosted tools, or remote resources are required.
  How to use: verify server is enabled, authenticate if required, then call the server's tools/resources instead of ad-hoc HTTP requests.

- openapi (mcp_server:openapi)
  State: installed, enabled
  Description: OpenAPI MCP package exposing OctoAgent gateway endpoints as MCP resources/tools.
  Source: stdio
  Transport: stdio
  Command: /home/sieve-pub/public-workspace/octoagent/runtime/tools/mcp/node_modules/.bin/openapi-mcp-server
  Provides: mcp_server:openapi
  Requires: none
  When to use: external systems, hosted tools, or remote resources are required.
  How to use: verify server is enabled, authenticate if required, then call the server's tools/resources instead of ad-hoc HTTP requests.

- postgres (mcp_server:postgres)
  State: installed, enabled
  Description: PostgreSQL MCP using local socket connection.
  Source: stdio
  Transport: stdio
  Command: /home/sieve-pub/public-workspace/octoagent/runtime/tools/mcp/node_modules/.bin/mcp-server-postgres
  Provides: mcp_server:postgres
  Requires: none
  When to use: external systems, hosted tools, or remote resources are required.
  How to use: verify server is enabled, authenticate if required, then call the server's tools/resources instead of ad-hoc HTTP requests.

- redis (mcp_server:redis)
  State: installed, enabled
  Description: Redis MCP package connected to local Redis for cache/session key inspection.
  Source: stdio
  Transport: stdio
  Command: /home/sieve-pub/public-workspace/octoagent/runtime/tools/mcp/node_modules/.bin/mcp-server-redis
  Provides: mcp_server:redis
  Requires: none
  When to use: external systems, hosted tools, or remote resources are required.
  How to use: verify server is enabled, authenticate if required, then call the server's tools/resources instead of ad-hoc HTTP requests.

## Plugins (16)

- Agent Rules Skill Pack (plugin:agent-rules-skill-pack)
  State: installed, enabled
  Description: Curated engineering rules adapted from agent-rules-books for OctoAgent task planning, review, and code-quality decisions.
  Source: builtin
  Category: engineering
  Execution mode: advisory
  Review flow: plan, work, review
  Provides: arb:load-rules
  Requires: task_review, artifact_review, policy_review, task_workspace, agent_transcript, artifact_access
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- CloakBrowser Controlled Automation (plugin:cloakbrowser-controlled-automation)
  State: installed, enabled
  Description: Controlled browser automation template for explicitly authorized web tasks; disabled for bypass-oriented defaults.
  Source: builtin
  Category: integration
  Execution mode: tooling
  Review flow: plan, runtime, review
  Provides: cloak:browser-plan
  Requires: tool_invocation, artifact_write, policy_review, task_workspace, tool_registry, approval_policy, browser_runtime, user_authorization
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- Compound Engineering Review (plugin:compound-engineering-review)
  State: installed, enabled
  Description: Review-oriented engineering workflow plugin with explicit plan, work, review, and compound capture stages.
  Source: builtin
  Category: engineering
  Execution mode: workflow
  Review flow: brainstorm, plan, work, review, compound
  Provides: ce:brainstorm, ce:plan, ce:review
  Requires: task_review, artifact_review, policy_review, task_workspace, agent_transcript, artifact_access
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- Cheat On Content Workflow (plugin:content-experiment-workflow)
  State: installed, enabled
  Description: Content experiment workflow inspired by cheat-on-content: score, blind-predict, publish, measure, and retro.
  Source: builtin
  Category: engineering
  Execution mode: workflow
  Review flow: plan, work, review
  Provides: coc:experiment
  Requires: task_review, artifact_review, policy_review, task_workspace, agent_transcript, artifact_access
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- Fireworks Tech Graph Toolkit (plugin:diagram-generation-toolkit)
  State: installed, enabled
  Description: Technical diagram generation workflow for architecture, UML, and agent workflow artifacts.
  Source: builtin
  Category: integration
  Execution mode: tooling
  Review flow: plan, work, review
  Provides: ftg:diagram
  Requires: tool_invocation, artifact_write, policy_review, task_workspace, tool_registry, approval_policy, image_or_svg_output, artifact_access
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- Goalbuddy Workflow (plugin:goalbuddy-workflow)
  State: installed, enabled
  Description: Goal-contract workflow for turning ambiguous user requests into bounded agent tasks with success checks.
  Source: builtin
  Category: engineering
  Execution mode: workflow
  Review flow: brainstorm, plan, work, review
  Provides: goal:plan
  Requires: task_review, artifact_review, policy_review, task_workspace, agent_transcript, artifact_access
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- Beautiful HTML Deck Generator (plugin:html-deck-generator)
  State: installed, enabled
  Description: HTML slide template workflow for polished reports, courseware, and project summaries.
  Source: builtin
  Category: integration
  Execution mode: tooling
  Review flow: plan, work, review
  Provides: bht:deck
  Requires: tool_invocation, artifact_write, policy_review, task_workspace, tool_registry, approval_policy, artifact_access, webui_preview
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- Ian Handdrawn PPT (plugin:ian-handdrawn-ppt)
  State: installed, enabled
  Description: Chinese hand-drawn technical explanation image deck workflow for covers, pages, and contact sheets.
  Source: builtin
  Category: integration
  Execution mode: tooling
  Review flow: plan, work, review
  Provides: ian:blueprint
  Requires: tool_invocation, artifact_write, policy_review, task_workspace, tool_registry, approval_policy, image_generation_model, artifact_access
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- Lightseek SMG Gateway (plugin:lightseek-smg-gateway)
  State: installed, enabled
  Description: Model gateway integration reference for routing, OpenAI/Anthropic compatibility, MCP, tenancy, and tokenization caching.
  Source: builtin
  Category: runtime
  Execution mode: tooling
  Review flow: plan, runtime, review
  Provides: smg:gateway-plan
  Requires: runtime_bind, approval_review, task_graph_access, task_workspace, orchestration_graph, system_execution_policy, model_gateway, routing_policy
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- Lumibot Research Strategy (plugin:lumibot-research-strategy)
  State: installed, enabled
  Description: Backtestable trading-agent workflow integrated for research and paper-trading strategy design only.
  Source: builtin
  Category: integration
  Execution mode: workflow
  Review flow: plan, work, review
  Provides: lumibot:strategy-plan
  Requires: tool_invocation, artifact_write, policy_review, task_workspace, tool_registry, approval_policy, market_data_config, paper_trading_only
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- Mirage VFS Bridge (plugin:mirage-vfs-bridge)
  State: installed, enabled
  Description: Virtual filesystem bridge concept for exposing task workspaces, artifacts, and long-running context to agents.
  Source: builtin
  Category: runtime
  Execution mode: tooling
  Review flow: plan, runtime, review
  Provides: mirage:vfs-plan
  Requires: runtime_bind, approval_review, task_graph_access, task_workspace, orchestration_graph, system_execution_policy, filesystem_policy
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- Peekaboo Vision MCP (plugin:peekaboo-vision-mcp)
  State: installed, enabled
  Description: Screen capture and visual QA MCP template with a platform-neutral OctoAgent workflow.
  Source: builtin
  Category: integration
  Execution mode: tooling
  Review flow: plan, runtime, review
  Provides: peekaboo:capture-plan
  Requires: tool_invocation, artifact_write, policy_review, task_workspace, tool_registry, approval_policy, mcp_loader, screen_capture_runtime
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- Photo Agents Vision Workflow (plugin:photo-agents-vision-workflow)
  State: installed, enabled
  Description: Vision-grounded agent workflow with layered memory and self-written skill checkpoints.
  Source: builtin
  Category: engineering
  Execution mode: workflow
  Review flow: plan, work, review
  Provides: photo:workflow
  Requires: task_review, artifact_review, policy_review, task_workspace, agent_transcript, artifact_access
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- TokenSpeed Model Benchmark (plugin:tokenspeed-model-benchmark)
  State: installed, enabled
  Description: LLM inference benchmark workflow for model backend experiments on GPU hosts.
  Source: builtin
  Category: runtime
  Execution mode: tooling
  Review flow: plan, runtime, review
  Provides: tokenspeed:benchmark-plan
  Requires: runtime_bind, approval_review, task_graph_access, task_workspace, orchestration_graph, system_execution_policy, gpu_runtime, model_benchmark_policy
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- WITR Runtime Diagnostics (plugin:witr-runtime-diagnostics)
  State: installed, enabled
  Description: Runtime process explanation workflow for answering why a service or process is running.
  Source: builtin
  Category: runtime
  Execution mode: tooling
  Review flow: runtime, review
  Provides: witr:diagnose
  Requires: runtime_bind, approval_review, task_graph_access, task_workspace, orchestration_graph, system_execution_policy, process_snapshot
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

- Workspace Runtime Bridge (plugin:workspace-runtime-bridge)
  State: installed, enabled
  Description: Bind task-workspace cards to runtime-facing command surfaces and approvals.
  Source: builtin
  Category: runtime
  Execution mode: workflow
  Review flow: plan, runtime, review
  Provides: wrb:bind, wrb:review
  Requires: runtime_bind, approval_review, task_graph_access, task_workspace, orchestration_graph, system_execution_policy
  When to use: the requested capability already exists as an installed plugin or command set.
  How to use: prefer the plugin command IDs listed in Provides before recreating the behavior manually.

## Skills (51)

- agent-rules-books (skill:public:agent-rules-books)
  State: installed, enabled
  Description: Agent rules and review heuristics adapted for OctoAgent coding agents.
  Source: skills/public/agent-rules-books
  Category: public
  Skill file: agent-rules-books
  Provides: skill:agent-rules-books
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- autoresearch (skill:public:autoresearch)
  State: installed, enabled
  Description: 'Autonomous iterative experimentation loop for any programming task. Guides the user through defining goals, measurable metrics, and scope constraints, then runs an autonomous loop of code changes, testing, measuring, and keeping/discarding results. Inspired by Karpathy''s autoresearch. USE FOR: autonomous improvement, iterative optimization, experiment loop, auto research, performance tuning, automated experimentation, hill climbing, try things automatically, optimize code, run experiments, autonomous coding loop. DO NOT USE FOR: one-shot tasks, simple bug fixes, code review, or tasks without a measurable metric.'
  Source: skills/public/autoresearch
  Category: public
  Skill file: autoresearch
  Provides: skill:autoresearch
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- awesome-design-md (skill:public:awesome-design-md)
  State: installed, enabled
  Description: Default design-governance skill for UI, frontend, landing page, dashboard, component, HTML/CSS, React, Vue, and design-system work. Use when the task involves visual design, UX polish, interface review, or converting product intent into a high-quality screen.
  Source: skills/public/awesome-design-md
  Category: public
  Skill file: awesome-design-md
  Provides: skill:awesome-design-md
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- azure-ad-broker (skill:public:azure-ad-broker)
  State: installed, enabled
  Description: Plan-only Azure AD / Entra ID provisioning broker: emits Microsoft Graph user + group + license + MFA-enforcement request envelopes for tenant admin execution. OctoAgent never calls Graph directly.
  Source: skills/public/azure-ad-broker
  Category: public
  Skill file: azure-ad-broker
  Provides: skill:azure-ad-broker
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- bamboohr-broker (skill:public:bamboohr-broker)
  State: installed, enabled
  Description: Plan-only BambooHR onboarding broker: produces a signed-intent envelope (HTTP request payload + auth placeholders) for tenant admins to execute out-of-band. OctoAgent never calls BambooHR APIs directly.
  Source: skills/public/bamboohr-broker
  Category: public
  Skill file: bamboohr-broker
  Provides: skill:bamboohr-broker
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- beautiful-html-templates (skill:public:beautiful-html-templates)
  State: installed, enabled
  Description: HTML deck and slide template selection skill for reports and courseware.
  Source: skills/public/beautiful-html-templates
  Category: public
  Skill file: beautiful-html-templates
  Provides: skill:beautiful-html-templates
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- bootstrap (skill:public:bootstrap)
  State: installed, enabled
  Description: Generate a personalized SOUL.md through a warm, adaptive onboarding conversation. Trigger when the user wants to create, set up, or initialize their AI partner's identity — e.g., "create my SOUL.md", "bootstrap my agent", "set up my AI partner", "define who you are", "let's do onboarding", "personalize this AI", "make you mine", or when a SOUL.md is missing. Also trigger for updates: "update my SOUL.md", "change my AI's personality", "tweak the soul".
  Source: skills/public/bootstrap
  Category: public
  Skill file: bootstrap
  Provides: skill:bootstrap
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- chart-visualization (skill:public:chart-visualization)
  State: installed, enabled
  Description: This skill should be used when the user wants to visualize data. It intelligently selects the most suitable chart type from 26 available options, extracts parameters based on detailed specifications, and generates a chart image using a JavaScript script.
  Source: skills/public/chart-visualization
  Category: public
  Skill file: chart-visualization
  Provides: skill:chart-visualization
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- cheat-on-content (skill:public:cheat-on-content)
  State: installed, enabled
  Description: Content experiment skill for calibrated publishing workflows.
  Source: skills/public/cheat-on-content
  Category: public
  Skill file: cheat-on-content
  Provides: skill:cheat-on-content
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- claude-to-octopusagent (skill:public:claude-to-octopusagent)
  State: installed, enabled
  Description: "Interact with OctopusAgent AI agent platform via its HTTP API. Use this skill when the user wants to send messages or questions to OctopusAgent for research/analysis, start a OctopusAgent conversation thread, check OctopusAgent status or health, list available models/skills/agents in OctopusAgent, manage OctopusAgent memory, upload files to OctopusAgent threads, or delegate complex research tasks to OctopusAgent. Also use when the user mentions octopusagent, octopusagent, or wants to run a deep research task that OctopusAgent can handle."
  Source: skills/public/claude-to-octopusagent
  Category: public
  Skill file: claude-to-octopusagent
  Provides: skill:claude-to-octopusagent
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- cloakbrowser-controlled-browser (skill:public:cloakbrowser-controlled-browser)
  State: installed, enabled
  Description: Default browser tool for general web automation without explicit authorization required.
  Source: skills/public/cloakbrowser-controlled-browser
  Category: public
  Skill file: cloakbrowser-controlled-browser
  Provides: skill:cloakbrowser-controlled-browser
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- consulting-analysis (skill:public:consulting-analysis)
  State: installed, enabled
  Description: Use this skill when the user requests to generate, create, or write professional research reports including but not limited to market analysis, consumer insights, brand analysis, financial analysis, industry research, competitive intelligence, investment due diligence, or any consulting-grade analytical report. This skill operates in two phases — (1) generating a structured analysis framework with chapter skeleton, data query requirements, and analysis logic, and (2) after data collection by other skills, producing the final consulting-grade report with structured narratives, embedded charts, and strategic insights.
  Source: skills/public/consulting-analysis
  Category: public
  Skill file: consulting-analysis
  Provides: skill:consulting-analysis
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- data-analysis (skill:public:data-analysis)
  State: installed, enabled
  Description: Use this skill when the user uploads Excel (.xlsx/.xls) or CSV files and wants to perform data analysis, generate statistics, create summaries, pivot tables, SQL queries, or any form of structured data exploration. Supports multi-sheet Excel workbooks, aggregation, filtering, joins, and exporting results to CSV/JSON/Markdown.
  Source: skills/public/data-analysis
  Category: public
  Skill file: data-analysis
  Provides: skill:data-analysis
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- deep-research (skill:public:deep-research)
  State: installed, enabled
  Description: Use this skill instead of WebSearch for ANY question requiring web research. Trigger on queries like "what is X", "explain X", "compare X and Y", "research X", or before content generation tasks. Provides systematic multi-angle research methodology instead of single superficial searches. Use this proactively when the user's question needs online information.
  Source: skills/public/deep-research
  Category: public
  Skill file: deep-research
  Provides: skill:deep-research
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- employment-contract-blueprint (skill:public:employment-contract-blueprint)
  State: installed, enabled
  Description: Jurisdiction-aware employment-contract clause blueprint: enumerates required clauses (probation, IP, non-compete, severance, notice, working hours, leave, confidentiality, dispute resolution) and emits a structured outline. NEVER produces binding contract text; attorney review is mandatory.
  Source: skills/public/employment-contract-blueprint
  Category: public
  Skill file: employment-contract-blueprint
  Provides: skill:employment-contract-blueprint
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- find-skills (skill:public:find-skills)
  State: installed, enabled
  Description: Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities. This skill should be used when the user is looking for functionality that might exist as an installable skill.
  Source: skills/public/find-skills
  Category: public
  Skill file: find-skills
  Provides: skill:find-skills
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- fireworks-tech-graph (skill:public:fireworks-tech-graph)
  State: installed, enabled
  Description: Technical diagram generation skill for architecture and workflow visuals.
  Source: skills/public/fireworks-tech-graph
  Category: public
  Skill file: fireworks-tech-graph
  Provides: skill:fireworks-tech-graph
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- frontend-design (skill:public:frontend-design)
  State: installed, enabled
  Description: Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, artifacts, posters, or applications (examples include websites, landing pages, dashboards, React components, HTML/CSS layouts, or when styling/beautifying any web UI). Generates creative, polished code and UI design that avoids generic AI aesthetics.
  Source: skills/public/frontend-design
  Category: public
  Skill file: frontend-design
  Provides: skill:frontend-design
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- fullstack-dev (skill:public:fullstack-dev)
  State: installed, enabled
  Description: Adapted default MiniMax full-stack architecture skill for OctoAgent. Use this when a task spans backend and frontend integration, APIs, auth, uploads, realtime flows, or production hardening.
  Source: skills/public/fullstack-dev
  Category: public
  Skill file: fullstack-dev
  Provides: skill:fullstack-dev
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- get-shit-done (skill:public:get-shit-done)
  State: installed, enabled
  Description: 'Pragmatic, no-nonsense coding discipline. Cuts through analysis paralysis, scope creep, and over-engineering. USE FOR: when stuck, when a task is stalling, when scope keeps growing, when you need to ship, when perfection is blocking progress. DO NOT USE FOR: greenfield architecture decisions, security-critical systems where shortcuts are dangerous, team-wide standards changes.'
  Source: skills/public/get-shit-done
  Category: public
  Skill file: get-shit-done
  Provides: skill:get-shit-done
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- github-deep-research (skill:public:github-deep-research)
  State: installed, enabled
  Description: Conduct multi-round deep research on any GitHub Repo. Use when users request comprehensive analysis, timeline reconstruction, competitive analysis, or in-depth investigation of GitHub. Produces structured markdown reports with executive summaries, chronological timelines, metrics analysis, and Mermaid diagrams. Triggers on Github repository URL or open source projects.
  Source: skills/public/github-deep-research
  Category: public
  Skill file: github-deep-research
  Provides: skill:github-deep-research
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- goalbuddy (skill:public:goalbuddy)
  State: installed, enabled
  Description: Goal contract skill for bounded autonomous agent work.
  Source: skills/public/goalbuddy
  Category: public
  Skill file: goalbuddy
  Provides: skill:goalbuddy
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- google-workspace-broker (skill:public:google-workspace-broker)
  State: installed, enabled
  Description: Plan-only Google Workspace provisioning broker: emits Directory API user + group + license + 2SV-enforcement request envelopes for tenant admin execution. OctoAgent never calls Directory API directly.
  Source: skills/public/google-workspace-broker
  Category: public
  Skill file: google-workspace-broker
  Provides: skill:google-workspace-broker
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- gusto-broker (skill:public:gusto-broker)
  State: installed, enabled
  Description: Plan-only Gusto onboarding broker: produces a signed-intent REST envelope for new-hire create + payroll setup, for tenant admin out-of-band dispatch. OctoAgent never calls Gusto directly.
  Source: skills/public/gusto-broker
  Category: public
  Skill file: gusto-broker
  Provides: skill:gusto-broker
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- ian-handdrawn-ppt (skill:public:ian-handdrawn-ppt)
  State: installed, enabled
  Description: Chinese hand-drawn technical image deck skill for covers, pages, and contact sheets.
  Source: skills/public/ian-handdrawn-ppt
  Category: public
  Skill file: ian-handdrawn-ppt
  Provides: skill:ian-handdrawn-ppt
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- image-generation (skill:public:image-generation)
  State: installed, enabled
  Description: Use this skill when the user requests to generate, create, imagine, or visualize images including characters, scenes, products, or any visual content. Supports structured prompts and reference images for guided generation.
  Source: skills/public/image-generation
  Category: public
  Skill file: image-generation
  Provides: skill:image-generation
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- lightseek-smg-gateway (skill:public:lightseek-smg-gateway)
  State: installed, enabled
  Description: Model gateway routing skill for SMG-style experiments.
  Source: skills/public/lightseek-smg-gateway
  Category: public
  Skill file: lightseek-smg-gateway
  Provides: skill:lightseek-smg-gateway
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- mirage-vfs (skill:public:mirage-vfs)
  State: installed, enabled
  Description: Virtual filesystem planning skill for agent workspaces and task artifacts.
  Source: skills/public/mirage-vfs
  Category: public
  Skill file: mirage-vfs
  Provides: skill:mirage-vfs
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- office-generation (skill:public:office-generation)
  State: installed, enabled
  Description: Generate real Word, Excel, PowerPoint, PDF, and Markdown files from a structured JSON specification and save them in the current conversation output directory.
  Source: skills/public/office-generation
  Category: public
  Skill file: office-generation
  Provides: skill:office-generation
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- okta-broker (skill:public:okta-broker)
  State: installed, enabled
  Description: Plan-only Okta provisioning broker: emits Okta API user/create + group assignment + MFA-factor enrollment request envelopes for tenant admin execution. OctoAgent never calls Okta directly.
  Source: skills/public/okta-broker
  Category: public
  Skill file: okta-broker
  Provides: skill:okta-broker
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- peekaboo-vision-mcp (skill:public:peekaboo-vision-mcp)
  State: installed, enabled
  Description: Screen capture and visual QA skill for MCP-backed observation workflows.
  Source: skills/public/peekaboo-vision-mcp
  Category: public
  Skill file: peekaboo-vision-mcp
  Provides: skill:peekaboo-vision-mcp
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- pencil-design (skill:public:pencil-design)
  State: installed, enabled
  Description: Design UIs in Pencil (.pen files) and generate production code from them. Use when working with .pen files, designing screens or components in Pencil, or generating code from Pencil designs. Triggers on tasks involving Pencil, .pen files, design-to-code workflows, or UI design with the Pencil MCP tools.
  Source: skills/public/pencil-design
  Category: public
  Skill file: pencil-design
  Provides: skill:pencil-design
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- photo-agents (skill:public:photo-agents)
  State: installed, enabled
  Description: Vision-grounded workflow skill with layered memory and self-written skills.
  Source: skills/public/photo-agents
  Category: public
  Skill file: photo-agents
  Provides: skill:photo-agents
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- podcast-generation (skill:public:podcast-generation)
  State: installed, enabled
  Description: Use this skill when the user requests to generate, create, or produce podcasts from text content. Converts written content into a two-host conversational podcast audio format with natural dialogue.
  Source: skills/public/podcast-generation
  Category: public
  Skill file: podcast-generation
  Provides: skill:podcast-generation
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- ppt-generation (skill:public:ppt-generation)
  State: installed, enabled
  Description: Use this skill when the user requests to generate, create, or make presentations (PPT/PPTX). Creates visually rich slides by generating images for each slide and composing them into a PowerPoint file.
  Source: skills/public/ppt-generation
  Category: public
  Skill file: ppt-generation
  Provides: skill:ppt-generation
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- semgrep:scan (skill:public:semgrep:scan)
  State: installed, enabled
  Description: Run Semgrep security scans before or during security-sensitive coding work, especially changes involving auth, secrets, network access, shell execution, file handling, deserialization, dependencies, or CI/CD workflows.
  Source: skills/public/semgrep-scan
  Category: public
  Skill file: semgrep-scan
  Provides: skill:semgrep:scan
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- skill-creator (skill:public:skill-creator)
  State: installed, enabled
  Description: Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.
  Source: skills/public/skill-creator
  Category: public
  Skill file: skill-creator
  Provides: skill:skill-creator
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- smb-cs-playbook (skill:public:smb-cs-playbook)
  State: installed, enabled
  Description: Plan-only SMB customer-success playbook: kickoff agenda, 30/60/90 health-check templates, escalation paths, QBR template, churn-save runbook.
  Source: skills/public/smb-cs-playbook
  Category: public
  Skill file: smb-cs-playbook
  Provides: skill:smb-cs-playbook
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- smb-finance-close (skill:public:smb-finance-close)
  State: installed, enabled
  Description: Plan-only SMB month-end close playbook: bank recon, accruals, revenue cutoff, expense classification, tax provision check, close packet, audit trail review.
  Source: skills/public/smb-finance-close
  Category: public
  Skill file: smb-finance-close
  Provides: skill:smb-finance-close
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- smb-hr-onboarding (skill:public:smb-hr-onboarding)
  State: installed, enabled
  Description: Use this skill when a small or medium business (SMB) user needs to design, run, or audit a new-employee onboarding workflow. The skill produces a structured onboarding plan covering Day −7 → Day 30, including offer-letter checklist, equipment provisioning, accounts/access provisioning, compliance and policy delivery, first-week training agenda, mentor pairing, and Day-30 review. The skill is policy-aware (regional labor law, data-privacy, accessibility) and always produces a draft that requires explicit HR sign-off before any external side effects (sending offer letters, granting accounts, ordering hardware) are executed.
  Source: skills/public/smb-hr-onboarding
  Category: public
  Skill file: smb-hr-onboarding
  Provides: skill:smb-hr-onboarding
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- smb-it-helpdesk-runbook (skill:public:smb-it-helpdesk-runbook)
  State: installed, enabled
  Description: Plan-only SMB IT helpdesk runbook: ticket triage, priority matrix, password reset SOP, equipment request SOP, access request SOP, escalation paths, SLA definitions.
  Source: skills/public/smb-it-helpdesk-runbook
  Category: public
  Skill file: smb-it-helpdesk-runbook
  Provides: skill:smb-it-helpdesk-runbook
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- smb-sales-motion (skill:public:smb-sales-motion)
  State: installed, enabled
  Description: Plan-only SMB sales motion playbook: ICP definition, outbound cadence, discovery script, demo template, proposal template, negotiation guardrails, CS handoff packet.
  Source: skills/public/smb-sales-motion
  Category: public
  Skill file: smb-sales-motion
  Provides: skill:smb-sales-motion
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- spec-kit (skill:public:spec-kit)
  State: installed, enabled
  Description: 'Specification-driven development kit. Generates formal specs, BDD scenarios, acceptance criteria, and API contracts from requirements. USE FOR: writing specs, creating test plans, BDD/Given-When-Then scenarios, acceptance criteria, contract testing, spec-first API design, feature specifications, definition of done checklists. DO NOT USE FOR: one-off tasks without a spec, hotfixes, exploratory work without clear requirements.'
  Source: skills/public/spec-kit
  Category: public
  Skill file: spec-kit
  Provides: skill:spec-kit
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- surprise-me (skill:public:surprise-me)
  State: installed, enabled
  Description: Create a delightful, unexpected "wow" experience for the user by dynamically discovering and creatively combining other enabled skills. Triggers when the user says "surprise me" or any request expressing a desire for an unexpected creative showcase. Also triggers when the user is bored, wants inspiration, or asks for "something interesting".
  Source: skills/public/surprise-me
  Category: public
  Skill file: surprise-me
  Provides: skill:surprise-me
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- tokenspeed-benchmark (skill:public:tokenspeed-benchmark)
  State: installed, enabled
  Description: TokenSpeed benchmark planning skill for LLM inference experiments.
  Source: skills/public/tokenspeed-benchmark
  Category: public
  Skill file: tokenspeed-benchmark
  Provides: skill:tokenspeed-benchmark
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- vercel-deploy (skill:public:vercel-deploy)
  State: installed, enabled
  Description: Deploy applications and websites to Vercel. Use this skill when the user requests deployment actions such as "Deploy my app", "Deploy this to production", "Create a preview deployment", "Deploy and give me the link", or "Push this live". No authentication required - returns preview URL and claimable deployment link.
  Source: skills/public/vercel-deploy-claimable
  Category: public
  Skill file: vercel-deploy-claimable
  Provides: skill:vercel-deploy
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- video-generation (skill:public:video-generation)
  State: installed, enabled
  Description: Use this skill when the user requests to generate, create, or imagine videos. Supports structured prompts and reference image for guided generation.
  Source: skills/public/video-generation
  Category: public
  Skill file: video-generation
  Provides: skill:video-generation
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- voltagent-best-practices (skill:public:voltagent-best-practices)
  State: installed, enabled
  Description: VoltAgent architectural patterns and conventions. Covers agents vs workflows, project layout, memory, servers, and observability.
  Source: skills/public/voltagent-best-practices
  Category: public
  Skill file: voltagent-best-practices
  Provides: skill:voltagent-best-practices
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- web-design-guidelines (skill:public:web-design-guidelines)
  State: installed, enabled
  Description: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
  Source: skills/public/web-design-guidelines
  Category: public
  Skill file: web-design-guidelines
  Provides: skill:web-design-guidelines
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- witr-runtime-diagnosis (skill:public:witr-runtime-diagnosis)
  State: installed, enabled
  Description: Runtime diagnosis skill for explaining why processes and services are running.
  Source: skills/public/witr-runtime-diagnosis
  Category: public
  Skill file: witr-runtime-diagnosis
  Provides: skill:witr-runtime-diagnosis
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- workday-broker (skill:public:workday-broker)
  State: installed, enabled
  Description: Plan-only Workday onboarding broker: produces a signed-intent SOAP/REST envelope for the Hire business process. OctoAgent never calls Workday tenants directly; output is an artifact for a credentialed integration user.
  Source: skills/public/workday-broker
  Category: public
  Skill file: workday-broker
  Provides: skill:workday-broker
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

## Managed Tools (0)

## Maintenance

- Regeneration source: `backend/src/utils/agent_tool_guide.py`.
- Snapshot sources: capability registry plus `runtime/system_tools/*/manifest.json`.
- Regenerate after install/uninstall/enable/disable/configuration changes of any managed capability.
