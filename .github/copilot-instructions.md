# OctoAgent System Tool Guide

This file is auto-generated from the current OctoAgent runtime state.
Whenever skills, plugins, MCP servers, or hooks are added, removed, enabled, disabled, or reconfigured, this file must be regenerated immediately.

## System Rules

- Before using a specialized capability, prefer an installed skill/plugin/MCP server over ad-hoc behavior.
- If a requested capability is already installed, use it instead of recreating it.
- If a capability depends on runtime state, check installed/enabled state and activation blockers first.
- Before using a managed capability category, read the relevant section in this file and follow the listed interface contract.
- After any change to skills/plugins/MCP/hooks, regenerate this guide.

## Registry Summary

- Generated from: current runtime capability snapshot
- Total capabilities: 108
- Enabled capabilities: 97
- Installed capabilities: 108
- Channel: 10 total, 0 enabled
- MCP Servers: 3 total, 2 enabled
- Plugins: 2 total, 2 enabled
- Skills: 93 total, 93 enabled

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

## MCP Servers (3)

- firecrawl (mcp_server:firecrawl)
  State: installed, disabled
  Description: Firecrawl MCP server for structured web crawling and scraping. Requires FIRECRAWL_API_KEY.
  Source: stdio
  Transport: stdio
  Command: npx
  Provides: mcp_server:firecrawl
  Requires: none
  When to use: external systems, hosted tools, or remote resources are required.
  How to use: verify server is enabled, authenticate if required, then call the server's tools/resources instead of ad-hoc HTTP requests.

- prompts-chat (mcp_server:prompts-chat)
  State: installed, enabled
  Description: Remote prompts.chat MCP server from f/prompts.chat
  Source: http
  Transport: http
  URL: https://prompts.chat/api/mcp
  Provides: mcp_server:prompts-chat
  Requires: none
  When to use: external systems, hosted tools, or remote resources are required.
  How to use: verify server is enabled, authenticate if required, then call the server's tools/resources instead of ad-hoc HTTP requests.

- voltagent (mcp_server:voltagent)
  State: installed, enabled
  Source: stdio
  Transport: stdio
  Command: npx
  Provides: mcp_server:voltagent
  Requires: none
  When to use: external systems, hosted tools, or remote resources are required.
  How to use: verify server is enabled, authenticate if required, then call the server's tools/resources instead of ad-hoc HTTP requests.

## Plugins (2)

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

## Skills (93)

- agency-agents (skill:custom:agency-agents)
  State: installed, enabled
  Description: Upstream Agency Agents library converted into OctoAgent agent templates.
  Source: skills/custom/agency-agents
  Category: custom
  Skill file: agency-agents
  Provides: skill:agency-agents
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- agent-browser (skill:custom:agent-browser)
  State: installed, enabled
  Description: Use agent-controlled browser workflows for inspection, navigation, smoke validation, screenshots, and web task execution through the browser runtime.
  Source: skills/custom/agent-browser
  Category: custom
  Skill file: agent-browser
  Provides: skill:agent-browser
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- agent-ui (skill:custom:agent-ui)
  State: installed, enabled
  Description: Build and audit agent-facing WebUI surfaces, including governance dashboards, status states, confirmation flows, and operator ergonomics.
  Source: skills/custom/agent-ui
  Category: custom
  Skill file: agent-ui
  Provides: skill:agent-ui
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- ai-prompt-engineering-safety-review (skill:custom:ai-prompt-engineering-safety-review)
  State: installed, enabled
  Description: 'Comprehensive AI prompt engineering safety review and improvement prompt. Analyzes prompts for safety, bias, security vulnerabilities, and effectiveness while providing detailed improvement recommendations with extensive frameworks, testing methodologies, and educational content.'
  Source: skills/custom/ai-prompt-engineering-safety-review
  Category: custom
  Skill file: ai-prompt-engineering-safety-review
  Provides: skill:ai-prompt-engineering-safety-review
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- auto-research (skill:custom:auto-research)
  State: installed, enabled
  Description: '用于自动研究、文献检索、问题拆解、研究路线设计、实验清单规划。适合用户提出一个研究主题、论文方向、技术问题或对比目标时调用。关键词: auto research, literature review, survey, novelty check, experiment plan, research pipeline.'
  Source: skills/custom/auto-research
  Category: custom
  Skill file: auto-research
  Provides: skill:auto-research
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- awesome-chatgpt-prompt (skill:custom:awesome-chatgpt-prompt)
  State: installed, enabled
  Description: Prompt-library skill wrapper for prompts.chat, formerly Awesome ChatGPT Prompts.
  Source: skills/custom/awesome-chatgpt-prompt
  Category: custom
  Skill file: awesome-chatgpt-prompt
  Provides: skill:awesome-chatgpt-prompt
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

- azure-resource-health-diagnose (skill:custom:azure-resource-health-diagnose)
  State: installed, enabled
  Description: 'Analyze Azure resource health, diagnose issues from logs and telemetry, and create a remediation plan for identified problems.'
  Source: skills/custom/azure-resource-health-diagnose
  Category: custom
  Skill file: azure-resource-health-diagnose
  Provides: skill:azure-resource-health-diagnose
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

- breakdown-epic-arch (skill:custom:breakdown-epic-arch)
  State: installed, enabled
  Description: 'Prompt for creating the high-level technical architecture for an Epic, based on a Product Requirements Document.'
  Source: skills/custom/breakdown-epic-arch
  Category: custom
  Skill file: breakdown-epic-arch
  Provides: skill:breakdown-epic-arch
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- breakdown-epic-pm (skill:custom:breakdown-epic-pm)
  State: installed, enabled
  Description: 'Prompt for creating an Epic Product Requirements Document (PRD) for a new epic. This PRD will be used as input for generating a technical architecture specification.'
  Source: skills/custom/breakdown-epic-pm
  Category: custom
  Skill file: breakdown-epic-pm
  Provides: skill:breakdown-epic-pm
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- breakdown-feature-implementation (skill:custom:breakdown-feature-implementation)
  State: installed, enabled
  Description: 'Prompt for creating detailed feature implementation plans, following Epoch monorepo structure.'
  Source: skills/custom/breakdown-feature-implementation
  Category: custom
  Skill file: breakdown-feature-implementation
  Provides: skill:breakdown-feature-implementation
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- breakdown-feature-prd (skill:custom:breakdown-feature-prd)
  State: installed, enabled
  Description: 'Prompt for creating Product Requirements Documents (PRDs) for new features, based on an Epic.'
  Source: skills/custom/breakdown-feature-prd
  Category: custom
  Skill file: breakdown-feature-prd
  Provides: skill:breakdown-feature-prd
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- browser-use (skill:custom:browser-use)
  State: installed, enabled
  Description: Official browser-use skill for AI-assisted browser automation.
  Source: skills/custom/browser-use
  Category: custom
  Skill file: browser-use
  Provides: skill:browser-use
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- browser-wing (skill:custom:browser-wing)
  State: installed, enabled
  Description: Browser automation wing for planning, launching, observing, and reporting browser-runtime tasks with fallback from desktop stubs to real browser APIs.
  Source: skills/custom/browser-wing
  Category: custom
  Skill file: browser-wing
  Provides: skill:browser-wing
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

- claude-to-octoagent (skill:public:claude-to-octoagent)
  State: installed, enabled
  Description: "Interact with OctoAgent AI agent platform via its HTTP API. Use this skill when the user wants to send messages or questions to OctoAgent for research/analysis, start a OctoAgent conversation thread, check OctoAgent status or health, list available models/skills/agents in OctoAgent, manage OctoAgent memory, upload files to OctoAgent threads, or delegate complex research tasks to OctoAgent. Also use when the user mentions octoagent, octoagent, or wants to run a deep research task that OctoAgent can handle."
  Source: skills/public/claude-to-octoagent
  Category: public
  Skill file: claude-to-octoagent
  Provides: skill:claude-to-octoagent
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- cli-mastery (skill:custom:cli-mastery)
  State: installed, enabled
  Description: 'Interactive training for the GitHub Copilot CLI. Guided lessons, quizzes, scenario challenges, and a full reference covering slash commands, shortcuts, modes, agents, skills, MCP, and configuration. Say "cliexpert" to start.'
  Source: skills/custom/cli-mastery
  Category: custom
  Skill file: cli-mastery
  Provides: skill:cli-mastery
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

- context-map (skill:custom:context-map)
  State: installed, enabled
  Description: 'Generate a map of all files relevant to a task before making changes'
  Source: skills/custom/context-map
  Category: custom
  Skill file: context-map
  Provides: skill:context-map
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- conventional-commit (skill:custom:conventional-commit)
  State: installed, enabled
  Description: 'Prompt and workflow for generating conventional commit messages using a structured XML format. Guides users to create standardized, descriptive commit messages in line with the Conventional Commits specification, including instructions, examples, and validation.'
  Source: skills/custom/conventional-commit
  Category: custom
  Skill file: conventional-commit
  Provides: skill:conventional-commit
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- copilot-sdk (skill:custom:copilot-sdk)
  State: installed, enabled
  Description: Build agentic applications with GitHub Copilot SDK. Use when embedding AI agents in apps, creating custom tools, implementing streaming responses, managing sessions, connecting to MCP servers, or creating custom agents. Triggers on Copilot SDK, GitHub SDK, agentic app, embed Copilot, programmable agent, MCP server, custom agent.
  Source: skills/custom/copilot-sdk
  Category: custom
  Skill file: copilot-sdk
  Provides: skill:copilot-sdk
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- create-agentsmd (skill:custom:create-agentsmd)
  State: installed, enabled
  Description: 'Prompt for generating an AGENTS.md file for a repository'
  Source: skills/custom/create-agentsmd
  Category: custom
  Skill file: create-agentsmd
  Provides: skill:create-agentsmd
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- create-github-issues-feature-from-implementation-plan (skill:custom:create-github-issues-feature-from-implementation-plan)
  State: installed, enabled
  Description: 'Create GitHub Issues from implementation plan phases using feature_request.yml or chore_request.yml templates.'
  Source: skills/custom/create-github-issues-feature-from-implementation-plan
  Category: custom
  Skill file: create-github-issues-feature-from-implementation-plan
  Provides: skill:create-github-issues-feature-from-implementation-plan
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- create-implementation-plan (skill:custom:create-implementation-plan)
  State: installed, enabled
  Description: 'Create a new implementation plan file for new features, refactoring existing code or upgrading packages, design, architecture or infrastructure.'
  Source: skills/custom/create-implementation-plan
  Category: custom
  Skill file: create-implementation-plan
  Provides: skill:create-implementation-plan
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- create-readme (skill:custom:create-readme)
  State: installed, enabled
  Description: 'Create a README.md file for the project'
  Source: skills/custom/create-readme
  Category: custom
  Skill file: create-readme
  Provides: skill:create-readme
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- create-specification (skill:custom:create-specification)
  State: installed, enabled
  Description: 'Create a new specification file for the solution, optimized for Generative AI consumption.'
  Source: skills/custom/create-specification
  Category: custom
  Skill file: create-specification
  Provides: skill:create-specification
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- create-technical-spike (skill:custom:create-technical-spike)
  State: installed, enabled
  Description: 'Create time-boxed technical spike documents for researching and resolving critical development decisions before implementation.'
  Source: skills/custom/create-technical-spike
  Category: custom
  Skill file: create-technical-spike
  Provides: skill:create-technical-spike
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- csharp-nunit (skill:custom:csharp-nunit)
  State: installed, enabled
  Description: 'Get best practices for NUnit unit testing, including data-driven tests'
  Source: skills/custom/csharp-nunit
  Category: custom
  Skill file: csharp-nunit
  Provides: skill:csharp-nunit
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

- declarative-agents (skill:custom:declarative-agents)
  State: installed, enabled
  Description: 'Complete development kit for Microsoft 365 Copilot declarative agents with three comprehensive workflows (basic, advanced, validation), TypeSpec support, and Microsoft 365 Agents Toolkit integration'
  Source: skills/custom/declarative-agents
  Category: custom
  Skill file: declarative-agents
  Provides: skill:declarative-agents
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

- delegate-task (skill:custom:delegate-task)
  State: installed, enabled
  Description: Delegate tasks to OpenSpace — a full-stack autonomous worker for coding, DevOps, web research, and desktop automation, backed by an extensive MCP tool and skill library. Skills auto-improve through use, reducing token consumption over time. A cloud community lets agents share and collectively evolve reusable skills.
  Source: skills/custom/delegate-task
  Category: custom
  Skill file: delegate-task
  Provides: skill:delegate-task
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

- first-ask (skill:custom:first-ask)
  State: installed, enabled
  Description: 'Interactive, input-tool powered, task refinement workflow: interrogates scope, deliverables, constraints before carrying out the task; Requires the Joyride extension.'
  Source: skills/custom/first-ask
  Category: custom
  Skill file: first-ask
  Provides: skill:first-ask
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

- gbrain (skill:custom:gbrain)
  State: installed, enabled
  Description: Persistent knowledge-capture discipline for agentic coding sessions. Use when a bug fix, gotcha, architectural constraint, or verified workaround should outlive the current conversation. Covers which memory scope to pick (/memories/, /memories/session/, /memories/repo/), how to phrase entries for fast recall, and when to prune stale notes.
  Source: skills/custom/gbrain
  Category: custom
  Skill file: gbrain
  Provides: skill:gbrain
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- generate-custom-instructions-from-codebase (skill:custom:generate-custom-instructions-from-codebase)
  State: installed, enabled
  Description: 'Migration and code evolution instructions generator for GitHub Copilot. Analyzes differences between two project versions (branches, commits, or releases) to create precise instructions allowing Copilot to maintain consistency during technology migrations, major refactoring, or framework version upgrades.'
  Source: skills/custom/generate-custom-instructions-from-codebase
  Category: custom
  Skill file: generate-custom-instructions-from-codebase
  Provides: skill:generate-custom-instructions-from-codebase
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- gh-cli (skill:custom:gh-cli)
  State: installed, enabled
  Description: GitHub CLI (gh) comprehensive reference for repositories, issues, pull requests, Actions, projects, releases, gists, codespaces, organizations, extensions, and all GitHub operations from the command line.
  Source: skills/custom/gh-cli
  Category: custom
  Skill file: gh-cli
  Provides: skill:gh-cli
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

- gstack (skill:custom:gstack)
  State: installed, enabled
  Description: Git stacked-branch discipline for slice-based refactors. Use when a change is too large for a single commit/PR and needs to be delivered as a stack of small, sequentially buildable slices. Covers branch naming, slice sizing, build+smoke-per-slice gates, rebase strategy, and cumulative push handling when the remote is flaky.
  Source: skills/custom/gstack
  Category: custom
  Skill file: gstack
  Provides: skill:gstack
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

- java-junit (skill:custom:java-junit)
  State: installed, enabled
  Description: 'Get best practices for JUnit 5 unit testing, including data-driven tests'
  Source: skills/custom/java-junit
  Category: custom
  Skill file: java-junit
  Provides: skill:java-junit
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- karpathy-autoresearch (skill:custom:karpathy-autoresearch)
  State: installed, enabled
  Description: Autonomous experimentation workflow adapted from karpathy/autoresearch.
  Source: skills/custom/karpathy-autoresearch
  Category: custom
  Skill file: karpathy-autoresearch
  Provides: skill:karpathy-autoresearch
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- karpathy-guidelines (skill:custom:karpathy-guidelines)
  State: installed, enabled
  Description: Use when writing, reviewing, or refactoring code and you need to avoid hidden assumptions, overengineering, broad unrelated edits, or vague success criteria. Encourages simple, surgical, verifiable work.
  Source: skills/custom/karpathy-guidelines
  Category: custom
  Skill file: karpathy-guidelines
  Provides: skill:karpathy-guidelines
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- llm-wiki (skill:custom:llm-wiki)
  State: installed, enabled
  Description: Create compact LLM-facing wiki pages from project knowledge, logs, docs, and run reports with citations, stale checks, and update guidance.
  Source: skills/custom/llm-wiki
  Category: custom
  Skill file: llm-wiki
  Provides: skill:llm-wiki
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- markitdown-convert (skill:custom:markitdown-convert)
  State: installed, enabled
  Description: Use when a local file needs to be converted into LLM-friendly Markdown for indexing, summarization, extraction, or analysis. Works best for HTML, PDF, Office docs, plain text, JSON, XML, and similar documents.
  Source: skills/custom/markitdown-convert
  Category: custom
  Skill file: markitdown-convert
  Provides: skill:markitdown-convert
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- mcp-cli (skill:custom:mcp-cli)
  State: installed, enabled
  Description: Interface for MCP (Model Context Protocol) servers via CLI. Use when you need to interact with external tools, APIs, or data sources through MCP servers, list available MCP servers/tools, or call MCP tools from command line.
  Source: skills/custom/mcp-cli
  Category: custom
  Skill file: mcp-cli
  Provides: skill:mcp-cli
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- mcp-configure (skill:custom:mcp-configure)
  State: installed, enabled
  Description: Configure an MCP server for GitHub Copilot with your Dataverse environment.
  Source: skills/custom/mcp-configure
  Category: custom
  Skill file: mcp-configure
  Provides: skill:mcp-configure
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- mcp-copilot-studio-server-generator (skill:custom:mcp-copilot-studio-server-generator)
  State: installed, enabled
  Description: 'Generate a complete MCP server implementation optimized for Copilot Studio integration with proper schema constraints and streamable HTTP support'
  Source: skills/custom/mcp-copilot-studio-server-generator
  Category: custom
  Skill file: mcp-copilot-studio-server-generator
  Provides: skill:mcp-copilot-studio-server-generator
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- mcp-create-adaptive-cards (skill:custom:mcp-create-adaptive-cards)
  State: installed, enabled
  Description: 'Skill converted from mcp-create-adaptive-cards.prompt.md'
  Source: skills/custom/mcp-create-adaptive-cards
  Category: custom
  Skill file: mcp-create-adaptive-cards
  Provides: skill:mcp-create-adaptive-cards
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- mcp-create-declarative-agent (skill:custom:mcp-create-declarative-agent)
  State: installed, enabled
  Description: 'Skill converted from mcp-create-declarative-agent.prompt.md'
  Source: skills/custom/mcp-create-declarative-agent
  Category: custom
  Skill file: mcp-create-declarative-agent
  Provides: skill:mcp-create-declarative-agent
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- mcp-deploy-manage-agents (skill:custom:mcp-deploy-manage-agents)
  State: installed, enabled
  Description: 'Skill converted from mcp-deploy-manage-agents.prompt.md'
  Source: skills/custom/mcp-deploy-manage-agents
  Category: custom
  Skill file: mcp-deploy-manage-agents
  Provides: skill:mcp-deploy-manage-agents
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- microsoft-code-reference (skill:custom:microsoft-code-reference)
  State: installed, enabled
  Description: Look up Microsoft API references, find working code samples, and verify SDK code is correct. Use when working with Azure SDKs, .NET libraries, or Microsoft APIs—to find the right method, check parameters, get working examples, or troubleshoot errors. Catches hallucinated methods, wrong signatures, and deprecated patterns by querying official docs.
  Source: skills/custom/microsoft-code-reference
  Category: custom
  Skill file: microsoft-code-reference
  Provides: skill:microsoft-code-reference
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- microsoft-docs (skill:custom:microsoft-docs)
  State: installed, enabled
  Description: 'Query official Microsoft documentation to find concepts, tutorials, and code examples across Azure, .NET, Agent Framework, Aspire, VS Code, GitHub, and more. Uses Microsoft Learn MCP as the default, with Context7 and Aspire MCP for content that lives outside learn.microsoft.com.'
  Source: skills/custom/microsoft-docs
  Category: custom
  Skill file: microsoft-docs
  Provides: skill:microsoft-docs
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- multi-stage-dockerfile (skill:custom:multi-stage-dockerfile)
  State: installed, enabled
  Description: 'Create optimized multi-stage Dockerfiles for any language or framework'
  Source: skills/custom/multi-stage-dockerfile
  Category: custom
  Skill file: multi-stage-dockerfile
  Provides: skill:multi-stage-dockerfile
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- openrelay (skill:custom:openrelay)
  State: installed, enabled
  Description: Design and operate relay-style integrations for channels, webhooks, worker callbacks, and cross-process event delivery with retry and audit hooks.
  Source: skills/custom/openrelay
  Category: custom
  Skill file: openrelay
  Provides: skill:openrelay
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- playwright-explore-website (skill:custom:playwright-explore-website)
  State: installed, enabled
  Description: 'Website exploration for testing using Playwright MCP'
  Source: skills/custom/playwright-explore-website
  Category: custom
  Skill file: playwright-explore-website
  Provides: skill:playwright-explore-website
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- playwright-generate-test (skill:custom:playwright-generate-test)
  State: installed, enabled
  Description: 'Generate a Playwright test based on a scenario using Playwright MCP'
  Source: skills/custom/playwright-generate-test
  Category: custom
  Skill file: playwright-generate-test
  Provides: skill:playwright-generate-test
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

- polyglot-test-agent (skill:custom:polyglot-test-agent)
  State: installed, enabled
  Description: 'Generates comprehensive, workable unit tests for any programming language using a multi-agent pipeline. Use when asked to generate tests, write unit tests, improve test coverage, add test coverage, create test files, or test a codebase. Supports C#, TypeScript, JavaScript, Python, Go, Rust, Java, and more. Orchestrates research, planning, and implementation phases to produce tests that compile, pass, and follow project conventions.'
  Source: skills/custom/polyglot-test-agent
  Category: custom
  Skill file: polyglot-test-agent
  Provides: skill:polyglot-test-agent
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- postgresql-code-review (skill:custom:postgresql-code-review)
  State: installed, enabled
  Description: 'PostgreSQL-specific code review assistant focusing on PostgreSQL best practices, anti-patterns, and unique quality standards. Covers JSONB operations, array usage, custom types, schema design, function optimization, and PostgreSQL-exclusive security features like Row Level Security (RLS).'
  Source: skills/custom/postgresql-code-review
  Category: custom
  Skill file: postgresql-code-review
  Provides: skill:postgresql-code-review
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- postgresql-optimization (skill:custom:postgresql-optimization)
  State: installed, enabled
  Description: 'PostgreSQL-specific development assistant focusing on unique PostgreSQL features, advanced data types, and PostgreSQL-exclusive capabilities. Covers JSONB operations, array types, custom types, range/geometric types, full-text search, window functions, and PostgreSQL extensions ecosystem.'
  Source: skills/custom/postgresql-optimization
  Category: custom
  Skill file: postgresql-optimization
  Provides: skill:postgresql-optimization
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

- refactor (skill:custom:refactor)
  State: installed, enabled
  Description: 'Surgical code refactoring to improve maintainability without changing behavior. Covers extracting functions, renaming variables, breaking down god functions, improving type safety, eliminating code smells, and applying design patterns. Less drastic than repo-rebuilder; use for gradual improvements.'
  Source: skills/custom/refactor
  Category: custom
  Skill file: refactor
  Provides: skill:refactor
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- refactor-plan (skill:custom:refactor-plan)
  State: installed, enabled
  Description: 'Plan a multi-file refactor with proper sequencing and rollback steps'
  Source: skills/custom/refactor-plan
  Category: custom
  Skill file: refactor-plan
  Provides: skill:refactor-plan
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- remember (skill:custom:remember)
  State: installed, enabled
  Description: 'Transforms lessons learned into domain-organized memory instructions (global or workspace). Syntax: `/remember [>domain [scope]] lesson clue` where scope is `global` (default), `user`, `workspace`, or `ws`.'
  Source: skills/custom/remember
  Category: custom
  Skill file: remember
  Provides: skill:remember
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- remotion-skills (skill:custom:remotion-skills)
  State: installed, enabled
  Description: Remotion best-practices guidance sourced from skills.sh/remotion-dev/skills.
  Source: skills/custom/remotion-skills
  Category: custom
  Skill file: remotion-skills
  Provides: skill:remotion-skills
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- repo-story-time (skill:custom:repo-story-time)
  State: installed, enabled
  Description: 'Generate a comprehensive repository summary and narrative story from commit history'
  Source: skills/custom/repo-story-time
  Category: custom
  Skill file: repo-story-time
  Provides: skill:repo-story-time
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- review-and-refactor (skill:custom:review-and-refactor)
  State: installed, enabled
  Description: 'Review and refactor code in your project according to defined instructions'
  Source: skills/custom/review-and-refactor
  Category: custom
  Skill file: review-and-refactor
  Provides: skill:review-and-refactor
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

- skill-discovery (skill:custom:skill-discovery)
  State: installed, enabled
  Description: Search for reusable skills across OpenSpace's local registry and cloud community. Reusing proven skills saves tokens, improves reliability, and extends your capabilities beyond built-in tools.
  Source: skills/custom/skill-discovery
  Category: custom
  Skill file: skill-discovery
  Provides: skill:skill-discovery
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- sql-code-review (skill:custom:sql-code-review)
  State: installed, enabled
  Description: 'Universal SQL code review assistant that performs comprehensive security, maintainability, and code quality analysis across all SQL databases (MySQL, PostgreSQL, SQL Server, Oracle). Focuses on SQL injection prevention, access control, code standards, and anti-pattern detection. Complements SQL optimization prompt for complete development coverage.'
  Source: skills/custom/sql-code-review
  Category: custom
  Skill file: sql-code-review
  Provides: skill:sql-code-review
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- sql-optimization (skill:custom:sql-optimization)
  State: installed, enabled
  Description: 'Universal SQL performance optimization assistant for comprehensive query tuning, indexing strategies, and database performance analysis across all SQL databases (MySQL, PostgreSQL, SQL Server, Oracle). Provides execution plan analysis, pagination optimization, batch operations, and performance monitoring guidance.'
  Source: skills/custom/sql-optimization
  Category: custom
  Skill file: sql-optimization
  Provides: skill:sql-optimization
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- structured-autonomy-generate (skill:custom:structured-autonomy-generate)
  State: installed, enabled
  Description: 'Structured Autonomy Implementation Generator Prompt'
  Source: skills/custom/structured-autonomy-generate
  Category: custom
  Skill file: structured-autonomy-generate
  Provides: skill:structured-autonomy-generate
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- structured-autonomy-implement (skill:custom:structured-autonomy-implement)
  State: installed, enabled
  Description: 'Structured Autonomy Implementation Prompt'
  Source: skills/custom/structured-autonomy-implement
  Category: custom
  Skill file: structured-autonomy-implement
  Provides: skill:structured-autonomy-implement
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- structured-autonomy-plan (skill:custom:structured-autonomy-plan)
  State: installed, enabled
  Description: 'Structured Autonomy Planning Prompt'
  Source: skills/custom/structured-autonomy-plan
  Category: custom
  Skill file: structured-autonomy-plan
  Provides: skill:structured-autonomy-plan
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- suggest-awesome-github-copilot-agents (skill:custom:suggest-awesome-github-copilot-agents)
  State: installed, enabled
  Description: 'Suggest relevant GitHub Copilot Custom Agents files from the awesome-copilot repository based on current repository context and chat history, avoiding duplicates with existing custom agents in this repository, and identifying outdated agents that need updates.'
  Source: skills/custom/suggest-awesome-github-copilot-agents
  Category: custom
  Skill file: suggest-awesome-github-copilot-agents
  Provides: skill:suggest-awesome-github-copilot-agents
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- suggest-awesome-github-copilot-instructions (skill:custom:suggest-awesome-github-copilot-instructions)
  State: installed, enabled
  Description: 'Suggest relevant GitHub Copilot instruction files from the awesome-copilot repository based on current repository context and chat history, avoiding duplicates with existing instructions in this repository, and identifying outdated instructions that need updates.'
  Source: skills/custom/suggest-awesome-github-copilot-instructions
  Category: custom
  Skill file: suggest-awesome-github-copilot-instructions
  Provides: skill:suggest-awesome-github-copilot-instructions
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- suggest-awesome-github-copilot-skills (skill:custom:suggest-awesome-github-copilot-skills)
  State: installed, enabled
  Description: 'Suggest relevant GitHub Copilot skills from the awesome-copilot repository based on current repository context and chat history, avoiding duplicates with existing skills in this repository, and identifying outdated skills that need updates.'
  Source: skills/custom/suggest-awesome-github-copilot-skills
  Category: custom
  Skill file: suggest-awesome-github-copilot-skills
  Provides: skill:suggest-awesome-github-copilot-skills
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- superpowers (skill:custom:superpowers)
  State: installed, enabled
  Description: Meta-skill for composing high-leverage OctoAgent capabilities, choosing the strongest available workflow, and validating tool readiness before action.
  Source: skills/custom/superpowers
  Category: custom
  Skill file: superpowers
  Provides: skill:superpowers
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

- typespec-api-operations (skill:custom:typespec-api-operations)
  State: installed, enabled
  Description: 'Add GET, POST, PATCH, and DELETE operations to a TypeSpec API plugin with proper routing, parameters, and adaptive cards'
  Source: skills/custom/typespec-api-operations
  Category: custom
  Skill file: typespec-api-operations
  Provides: skill:typespec-api-operations
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- typespec-create-agent (skill:custom:typespec-create-agent)
  State: installed, enabled
  Description: 'Generate a complete TypeSpec declarative agent with instructions, capabilities, and conversation starters for Microsoft 365 Copilot'
  Source: skills/custom/typespec-create-agent
  Category: custom
  Skill file: typespec-create-agent
  Provides: skill:typespec-create-agent
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- typespec-create-api-plugin (skill:custom:typespec-create-api-plugin)
  State: installed, enabled
  Description: 'Generate a TypeSpec API plugin with REST operations, authentication, and Adaptive Cards for Microsoft 365 Copilot'
  Source: skills/custom/typespec-create-api-plugin
  Category: custom
  Skill file: typespec-create-api-plugin
  Provides: skill:typespec-create-api-plugin
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- update-implementation-plan (skill:custom:update-implementation-plan)
  State: installed, enabled
  Description: 'Update an existing implementation plan file with new or update requirements to provide new features, refactoring existing code or upgrading packages, design, architecture or infrastructure.'
  Source: skills/custom/update-implementation-plan
  Category: custom
  Skill file: update-implementation-plan
  Provides: skill:update-implementation-plan
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

- update-specification (skill:custom:update-specification)
  State: installed, enabled
  Description: 'Update an existing specification file for the solution, optimized for Generative AI consumption based on new requirements or updates to any existing code.'
  Source: skills/custom/update-specification
  Category: custom
  Skill file: update-specification
  Provides: skill:update-specification
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

- vibe-coding-guide (skill:custom:vibe-coding-guide)
  State: installed, enabled
  Description: '用于把模糊想法快速收敛成可交付实现，但避免无约束地“边写边漂”。适合原型开发、功能试做、产品探索、快速界面搭建、从一句想法变成工程任务时调用。关键词: vibe coding, prototype, rapid iteration, scoped build, product exploration.'
  Source: skills/custom/vibe-coding-guide
  Category: custom
  Skill file: vibe-coding-guide
  Provides: skill:vibe-coding-guide
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

- what-context-needed (skill:custom:what-context-needed)
  State: installed, enabled
  Description: 'Ask Copilot what files it needs to see before answering a question'
  Source: skills/custom/what-context-needed
  Category: custom
  Skill file: what-context-needed
  Provides: skill:what-context-needed
  Requires: none
  When to use: the user task clearly matches this domain or workflow.
  How to use: read the skill SKILL.md file first, then follow its workflow before using generic tools.

## Maintenance

- Regeneration source: `backend/src/utils/agent_tool_guide.py`.
- Snapshot source: `backend/src/capability_core/registry.py`.
- Regenerate after install/uninstall/enable/disable/configuration changes of any managed capability.
