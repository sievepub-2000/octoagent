# OctoAgent Harness Tool Guide

This file is generated from the same live registry exposed by `/api/harness` and `list_capabilities`.

## Operating contract

- Prefer an enabled Harness capability over an ad-hoc external search or installation.
- Permission mode is enforced by the server at tool dispatch; unavailable tools are not callable.
- Refresh Harness after adding, removing, enabling, disabling, or updating a tool source.
- Install and remove operator-managed tools only through their lifecycle tools.

## Summary

- Built-in tools: 94
- MCP servers: 4 total, 4 enabled
- Skills: 51 total, 51 enabled
- Plugins: 16 total, 16 enabled
- Channels: 3 total, 0 enabled
- Managed tools: 0 total, 0 callable

## Built-in tools

- `artifact_cleanup` [system/builtin]: Preview or apply cleanup only inside policy-owned disposable artifact roots.
- `artifact_governance_status` [sandbox/builtin]: Show artifact ownership, protected paths, and the current retention policy.
- `ask_clarification` [sandbox/meta]: Ask the user for clarification when you need more information to proceed. Use this tool when you encounter situations where you cannot proceed without user input: - **Missing information**: Required details not provided (e.g., file paths, URLs, specific requirements) - **Ambiguous requirements**: Multiple valid interpretations exist - **Approach choices**: Several valid approaches exist and you need user preference - **Risky operations**: Destructive actions that need explicit confirmation (e.g., deleting files, modifying production) - **Suggestions**: You have a recommendation but want user approval before proceeding The execution will be interrupted and the question will be presented to the user. Wait for the user's response before continuing. When to use ask_clarification: - You need information that wasn't provided in the user's request - The requirement can be interpreted in multiple ways - Multiple valid implementation approaches exist - You're about to perform a potentially dangerous operation - You have a recommendation but need user approval Best practices: - Ask ONE clarification at a time for clarity - Be specific and clear in your question - Don't make assumptions when clarification is needed - For risky operations, ALWAYS ask for confirmation - After calling this tool, execution will be interrupted automatically
- `awesome_selfhosted` [sandbox/reference]: Find self-hosted SaaS development tools from a curated awesome-selfhosted-style catalog.
- `bandit_scan` [directory/builtin]: Run bandit Python security scan.
- `bash` [sandbox/file-io]: Execute a bash command in a Linux environment. - Use `python` to run Python code. - Use `pip install` to install Python packages.
- `browser_publisher` [system/publishing]: Use Playwright/browser-use-ready automation for publishing page dry-runs and guarded submissions.
- `chapter-drafter` [directory/writing]: Alias for chapter_drafter using the requested hyphenated tool name.
- `chapter_drafter` [directory/writing]: Draft a chapter planning scaffold before prose generation.
- `chapter_writer` [directory/writing]: Store generated chapter/article/paper prose as a managed project asset.
- `codex_cli` [system/meta]: Run OpenAI Codex CLI command on the server host.
- `config_drift_check` [directory/builtin]: Compare the current config snapshot with a previous config_drift_snapshot payload.
- `config_drift_snapshot` [directory/builtin]: Create a hash snapshot for OctoAgent configuration and documentation files.
- `convert_document` [sandbox/media]: Convert a document file to another format. Supported conversions: - Office files (docx, xlsx, pptx, pdf) → Markdown (via markitdown) - HTML files → Markdown (via markdownify) - Markdown files → HTML (via Python markdown) - CSV files → Markdown table - JSON files → formatted Markdown code block - Any text file → plain text extract
- `db_connect_check` [system/builtin]: Check PostgreSQL connectivity.
- `db_explain` [system/builtin]: Explain a read-only PostgreSQL query without executing writes.
- `db_migration_plan` [system/builtin]: Analyze a migration SQL string and produce a risk plan without applying it.
- `db_query_readonly` [system/builtin]: Run one read-only PostgreSQL query with timeout and row limit.
- `db_schema_introspect` [system/builtin]: Inspect PostgreSQL schema tables and columns.
- `dependency_audit` [directory/builtin]: Run available dependency audit commands and save full logs.
- `desktop_click` [system/builtin]: Click an absolute desktop coordinate.
- `desktop_driver_status` [system/builtin]: Return native desktop driver availability for pyautogui/xdotool.
- `desktop_hotkey` [system/builtin]: Press a desktop keyboard shortcut.
- `desktop_screenshot` [system/builtin]: Capture a native desktop screenshot to a runtime artifact.
- `desktop_scroll` [system/builtin]: Scroll the native desktop at the current cursor location.
- `desktop_type_text` [system/builtin]: Type text into the currently focused native desktop control.
- `docker_compose_apply` [system/builtin]: Apply a Docker Compose action after explicit approval.
- `docker_compose_plan` [system/builtin]: Validate/render a Docker Compose plan without applying it.
- `docker_images` [system/builtin]: List Docker images.
- `docker_inspect` [system/builtin]: Inspect a Docker object.
- `docker_logs` [system/builtin]: Read Docker container logs.
- `docker_ps` [system/builtin]: List Docker containers.
- `docker_status` [system/builtin]: Check Docker client and daemon availability.
- `flipbook` [system/builtin]: Create a browser flipbook artifact from image frames using the flipbook package.
- `frontend_typecheck` [directory/builtin]: Run frontend typecheck if package script exists, otherwise tsc noEmit.
- `git_apply_patch` [system/builtin]: Apply or check a unified git patch after approval.
- `git_branch` [sandbox/builtin]: List git branches.
- `git_commit_prepare` [directory/builtin]: Prepare a commit summary without creating a commit.
- `git_diff` [sandbox/builtin]: Show git diff.
- `git_fetch` [system/builtin]: Fetch a git remote after approval.
- `git_log` [sandbox/builtin]: Show recent git commits.
- `git_status` [sandbox/builtin]: Show git status for a repository.
- `github_tool_install` [system/builtin]: Install a pinned GitHub tool under runtime/system_tools after explicit approval.
- `host_file_manage` [system/builtin]: Manage files on the OctoAgent host, including external system paths.
- `host_shell` [system/builtin]: Run an unrestricted shell command on the OctoAgent host. This is the system-level escape hatch for sudo/systemctl/service/apt/pip, process inspection, internal-network tools, and other operator work.
- `html_to_canvas` [system/builtin]: Render HTML into a PNG or JPG artifact using the html-to-canvas package.
- `http_transfer` [system/builtin]: Upload to or download from HTTP/HTTPS endpoints, including internal hosts.
- `human_approval_gate` [directory/governance]: Require and record human approval before public publishing or account mutation.
- `image_search` [sandbox/builtin]: Search for images online. Use this tool BEFORE image generation to find reference images for characters, portraits, objects, scenes, or any content requiring visual accuracy. **When to use:** - Before generating character/portrait images: search for similar poses, expressions, styles - Before generating specific objects/products: search for accurate visual references - Before generating scenes/locations: search for architectural or environmental references - Before generating fashion/clothing: search for style and detail references The returned image URLs can be used as reference images in image generation to significantly improve quality.
- `inspect_octoagent_runtime` [sandbox/builtin]: Inspect this OctoAgent deployment through authoritative, sanitized runtime sources. Use this for OctoAgent self-checks instead of enumerating environment variables, filesystem directories, processes, or guessed API routes.
- `integrated_project_catalog` [sandbox/plugins]: List OctoAgent-integrated upstream project capabilities.
- `integrated_workflow_run` [directory/workflow]: Plan an OctoAgent integrated workflow and return a ready-to-execute dispatch payload. This tool is the deterministic planner for installed upstream-derived skills/plugins. It always returns a verified ``tool_call_sequence`` plus a ``dispatch`` payload that the lead agent can hand directly to ``task`` for end-to-end execution by a subagent — no manual reformatting required. Recommended chain pattern:: plan = integrated_workflow_run(workflow_id="...", prompt="...") # review plan["tool_call_sequence"] and plan["expected_artifacts"] # then, to actually execute: task(**plan["dispatch"]) The ``dispatch`` payload contains ``description``, ``prompt`` and ``subagent_type`` keys suitable for direct ``task(**dispatch)`` invocation. The planner itself produces no side effects regardless of ``dry_run``; side effects only occur after the lead agent issues the ``task`` call.
- `lint_run` [directory/builtin]: Run configured backend/frontend linters.
- `list_capabilities` [sandbox/builtin]: List installed runtime capabilities such as skills, plugins, MCP servers, and hooks. Use this before selecting a managed skill/plugin/MCP/hook so the agent can choose installed capabilities instead of guessing from stale prompt text.
- `ls` [sandbox/builtin]: List the contents of a directory up to 2 levels deep in tree format.
- `managed_tool_execute` [system/builtin]: Execute the registered entrypoint of one callable managed tool.
- `managed_tool_list` [sandbox/builtin]: List operator-installed tools from the same manifest source used by Harness.
- `managed_tool_uninstall` [system/builtin]: Uninstall one manifest-owned tool and remove its artifacts/cache/logs.
- `media_probe` [directory/builtin]: Inspect local image/audio/video/3D media metadata without modifying the file.
- `novel_project_store` [directory/writing]: Manage long-form writing project files for articles, novels, papers, and web serials.
- `octo_doctor` [system/builtin]: Unified OctoAgent doctor for Harness capabilities, memory, and services.
- `playwright_run` [directory/builtin]: Run frontend Playwright tests.
- `present_files` [sandbox/builtin]: Make files visible to the user for viewing and rendering in the client interface. When to use the present_files tool: - Making any file available for the user to view, download, or interact with - Presenting multiple related files at once - After creating files that should be presented to the user When NOT to use the present_files tool: - When you only need to read file contents for your own processing - For temporary or intermediate files not meant for user viewing Notes: - You should call this tool after creating files and moving them to the `/mnt/user-data/outputs` directory. - This tool can be safely called in parallel with other tools. State updates are handled by a reducer to prevent conflicts.
- `process_image` [sandbox/media]: Process an image file — resize, convert format, compress, or extract metadata. Supported operations: - "info" — return image metadata (size, format, mode, EXIF). - "resize" — resize to given width/height (preserves aspect if one is 0). - "convert" — convert to output_format (png, jpeg, webp). - "compress" — re-encode at given quality (1-100). - "thumbnail" — create a max 256 px thumbnail.
- `process_manage` [system/builtin]: List or signal host processes.
- `publication_auditor` [system/publishing]: Audit a published URL by collecting title, visible text preview, screenshot, and expected text match.
- `pytest_collect` [directory/builtin]: Collect pytest tests without running them.
- `pytest_run` [directory/builtin]: Run pytest with optional path and keyword filter.
- `python_package_install` [system/builtin]: Install Python packages with pip after explicit user confirmation.
- `read_file` [sandbox/builtin]: Read the contents of a text file. Use this to examine source code, configuration files, logs, or any text-based file.
- `read_webpage` [sandbox/web]: Fetch a web page and extract its main content as clean text or markdown. Modes: - "article" — extract main article content using Readability algorithm. - "markdown" — convert full HTML to markdown. - "raw" — return raw HTML (first 50 KB). - "links" — extract all hyperlinks with text and href.
- `runtime_health_report` [system/builtin]: Return a compact OctoAgent host/runtime health report.
- `secret_scan` [directory/builtin]: Scan text files for likely secrets and save full findings as an artifact.
- `security_audit_scan` [directory/builtin]: Scan OctoAgent-managed files for common secret and unsafe-token patterns.
- `setup_agent` [sandbox/builtin]: Setup the custom OctoAgent agent. Args: soul: Full SOUL.md content defining the agent's personality and behavior. description: One-line description of what the agent does.
- `ssh_copy` [system/builtin]: Copy files with scp after approval.
- `ssh_exec` [system/builtin]: Run a non-interactive command on an SSH host after approval.
- `ssh_hosts_list` [system/builtin]: List configured SSH hosts from the current user's SSH config.
- `ssh_probe` [system/builtin]: Probe non-interactive SSH connectivity to a configured host.
- `static_security_scan` [directory/builtin]: Run backend-venv-compatible static security checks. Combines Ruff security (S) rules and Bandit when available.
- `str_replace` [sandbox/builtin]: Replace a substring in a file with another substring. If `replace_all` is False (default), the substring to replace must appear **exactly once** in the file.
- `task` [directory/agents]: Delegate a task to a specialized subagent that runs in its own context. Subagents help you: - Preserve context by keeping exploration and implementation separate - Handle complex multi-step tasks autonomously - Execute commands or operations in isolated contexts Common subagent types: - **general-purpose**: A capable agent for complex, multi-step tasks that require both exploration and action. Use when the task requires complex reasoning, multiple dependent steps, or would benefit from isolated context. - **bash**: Command execution specialist for running bash commands. Use for git operations, build processes, or when command output would be verbose. Additional dynamically loaded subagent types may be available from the subagent catalog (for example agency-* roles). If an unknown type is requested, the tool returns the current catalog names. When to use this tool: - Complex tasks requiring multiple steps or tools - Tasks that produce verbose output - When you want to isolate context from the main conversation - Parallel research or exploration tasks When NOT to use this tool: - Simple, single-step operations (use tools directly) - Tasks requiring user interaction or clarification
- `tcp_connect` [system/builtin]: Open a raw TCP connection, including localhost and private networks.
- `trivy_scan` [directory/builtin]: Run Trivy filesystem/config scan.
- `web_fetch` [sandbox/web]: Fetch a web page and return readable markdown. Uses a safe layered reader: httpx/readability first, Scrapling on the same URL when anti-bot/login/JavaScript challenge text or blocked HTTP statuses are detected, and RSS feeds for known public feed fallbacks.
- `web_search` [sandbox/web]: Search the web with Tavily (falls back to DDG on failure).
- `webnovel-write` [directory/writing]: Alias for webnovel_write using the requested hyphenated tool name.
- `webnovel_write` [directory/writing]: Package a chapter/article/paper for web publication metadata and review.
- `wp_cli_publish` [system/publishing]: Publish or draft a WordPress post through WP-CLI.
- `write_file` [sandbox/builtin]: Write text content to a file.
- `writestory` [directory/writing]: Create a story bible and outline scaffold for fiction or narrative nonfiction.
- `writing_format_export` [directory/writing-export]: Convert Markdown/text writing assets to finished artifacts with Pandoc.
- `writing_review_suite` [directory/writing-review]: Run writing quality and safety review with textlint, Vale, and Presidio.
- `writing_toolchain_status` [sandbox/writing]: Report installed writing, publishing, review, and browser automation tools.

## MCP servers

- `docker-compose` [enabled, unknown, directory]: Local Docker Compose inspection MCP for version and compose config validation.
- `filesystem` [enabled, unknown, directory]: System-scoped filesystem MCP with full host filesystem access; guarded by chat permission mode.
- `openapi` [enabled, unknown, system]: OpenAPI MCP package exposing OctoAgent gateway endpoints as MCP resources/tools.
- `postgres` [enabled, unknown, system]: PostgreSQL MCP using local socket connection.

## Skills

- `agent-rules-books` [enabled, public]: Agent rules and review heuristics adapted for OctoAgent coding agents.
- `autoresearch` [enabled, public]: 'Autonomous iterative experimentation loop for any programming task. Guides the user through defining goals, measurable metrics, and scope constraints, then runs an autonomous loop of code changes, testing, measuring, and keeping/discarding results. Inspired by Karpathy''s autoresearch. USE FOR: autonomous improvement, iterative optimization, experiment loop, auto research, performance tuning, automated experimentation, hill climbing, try things automatically, optimize code, run experiments, autonomous coding loop. DO NOT USE FOR: one-shot tasks, simple bug fixes, code review, or tasks without a measurable metric.'
- `awesome-design-md` [enabled, public]: Default design-governance skill for UI, frontend, landing page, dashboard, component, HTML/CSS, React, Vue, and design-system work. Use when the task involves visual design, UX polish, interface review, or converting product intent into a high-quality screen.
- `azure-ad-broker` [enabled, public]: Plan-only Azure AD / Entra ID provisioning broker: emits Microsoft Graph user + group + license + MFA-enforcement request envelopes for tenant admin execution. OctoAgent never calls Graph directly.
- `bamboohr-broker` [enabled, public]: Plan-only BambooHR onboarding broker: produces a signed-intent envelope (HTTP request payload + auth placeholders) for tenant admins to execute out-of-band. OctoAgent never calls BambooHR APIs directly.
- `beautiful-html-templates` [enabled, public]: HTML deck and slide template selection skill for reports and courseware.
- `bootstrap` [enabled, public]: Generate a personalized SOUL.md through a warm, adaptive onboarding conversation. Trigger when the user wants to create, set up, or initialize their AI partner's identity — e.g., "create my SOUL.md", "bootstrap my agent", "set up my AI partner", "define who you are", "let's do onboarding", "personalize this AI", "make you mine", or when a SOUL.md is missing. Also trigger for updates: "update my SOUL.md", "change my AI's personality", "tweak the soul".
- `chart-visualization` [enabled, public]: This skill should be used when the user wants to visualize data. It intelligently selects the most suitable chart type from 26 available options, extracts parameters based on detailed specifications, and generates a chart image using a JavaScript script.
- `cheat-on-content` [enabled, public]: Content experiment skill for calibrated publishing workflows.
- `claude-to-octopusagent` [enabled, public]: "Interact with OctopusAgent AI agent platform via its HTTP API. Use this skill when the user wants to send messages or questions to OctopusAgent for research/analysis, start a OctopusAgent conversation thread, check OctopusAgent status or health, list available models/skills/agents in OctopusAgent, manage OctopusAgent memory, upload files to OctopusAgent threads, or delegate complex research tasks to OctopusAgent. Also use when the user mentions octopusagent, octopusagent, or wants to run a deep research task that OctopusAgent can handle."
- `cloakbrowser-controlled-browser` [enabled, public]: Default browser tool for general web automation without explicit authorization required.
- `consulting-analysis` [enabled, public]: Use this skill when the user requests to generate, create, or write professional research reports including but not limited to market analysis, consumer insights, brand analysis, financial analysis, industry research, competitive intelligence, investment due diligence, or any consulting-grade analytical report. This skill operates in two phases — (1) generating a structured analysis framework with chapter skeleton, data query requirements, and analysis logic, and (2) after data collection by other skills, producing the final consulting-grade report with structured narratives, embedded charts, and strategic insights.
- `data-analysis` [enabled, public]: Use this skill when the user uploads Excel (.xlsx/.xls) or CSV files and wants to perform data analysis, generate statistics, create summaries, pivot tables, SQL queries, or any form of structured data exploration. Supports multi-sheet Excel workbooks, aggregation, filtering, joins, and exporting results to CSV/JSON/Markdown.
- `deep-research` [enabled, public]: Use this skill instead of WebSearch for ANY question requiring web research. Trigger on queries like "what is X", "explain X", "compare X and Y", "research X", or before content generation tasks. Provides systematic multi-angle research methodology instead of single superficial searches. Use this proactively when the user's question needs online information.
- `employment-contract-blueprint` [enabled, public]: Jurisdiction-aware employment-contract clause blueprint: enumerates required clauses (probation, IP, non-compete, severance, notice, working hours, leave, confidentiality, dispute resolution) and emits a structured outline. NEVER produces binding contract text; attorney review is mandatory.
- `find-skills` [enabled, public]: Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities. This skill should be used when the user is looking for functionality that might exist as an installable skill.
- `fireworks-tech-graph` [enabled, public]: Technical diagram generation skill for architecture and workflow visuals.
- `frontend-design` [enabled, public]: Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, artifacts, posters, or applications (examples include websites, landing pages, dashboards, React components, HTML/CSS layouts, or when styling/beautifying any web UI). Generates creative, polished code and UI design that avoids generic AI aesthetics.
- `fullstack-dev` [enabled, public]: Adapted default MiniMax full-stack architecture skill for OctoAgent. Use this when a task spans backend and frontend integration, APIs, auth, uploads, realtime flows, or production hardening.
- `get-shit-done` [enabled, public]: 'Pragmatic, no-nonsense coding discipline. Cuts through analysis paralysis, scope creep, and over-engineering. USE FOR: when stuck, when a task is stalling, when scope keeps growing, when you need to ship, when perfection is blocking progress. DO NOT USE FOR: greenfield architecture decisions, security-critical systems where shortcuts are dangerous, team-wide standards changes.'
- `github-deep-research` [enabled, public]: Conduct multi-round deep research on any GitHub Repo. Use when users request comprehensive analysis, timeline reconstruction, competitive analysis, or in-depth investigation of GitHub. Produces structured markdown reports with executive summaries, chronological timelines, metrics analysis, and Mermaid diagrams. Triggers on Github repository URL or open source projects.
- `goalbuddy` [enabled, public]: Goal contract skill for bounded autonomous agent work.
- `google-workspace-broker` [enabled, public]: Plan-only Google Workspace provisioning broker: emits Directory API user + group + license + 2SV-enforcement request envelopes for tenant admin execution. OctoAgent never calls Directory API directly.
- `gusto-broker` [enabled, public]: Plan-only Gusto onboarding broker: produces a signed-intent REST envelope for new-hire create + payroll setup, for tenant admin out-of-band dispatch. OctoAgent never calls Gusto directly.
- `ian-handdrawn-ppt` [enabled, public]: Chinese hand-drawn technical image deck skill for covers, pages, and contact sheets.
- `image-generation` [enabled, public]: Use this skill when the user requests to generate, create, imagine, or visualize images including characters, scenes, products, or any visual content. Supports structured prompts and reference images for guided generation.
- `lightseek-smg-gateway` [enabled, public]: Model gateway routing skill for SMG-style experiments.
- `mirage-vfs` [enabled, public]: Virtual filesystem planning skill for agent workspaces and task artifacts.
- `office-generation` [enabled, public]: Generate real Word, Excel, PowerPoint, PDF, and Markdown files from a structured JSON specification and save them in the current conversation output directory.
- `okta-broker` [enabled, public]: Plan-only Okta provisioning broker: emits Okta API user/create + group assignment + MFA-factor enrollment request envelopes for tenant admin execution. OctoAgent never calls Okta directly.
- `peekaboo-vision-mcp` [enabled, public]: Screen capture and visual QA skill for MCP-backed observation workflows.
- `pencil-design` [enabled, public]: Design UIs in Pencil (.pen files) and generate production code from them. Use when working with .pen files, designing screens or components in Pencil, or generating code from Pencil designs. Triggers on tasks involving Pencil, .pen files, design-to-code workflows, or UI design with the Pencil MCP tools.
- `photo-agents` [enabled, public]: Vision-grounded workflow skill with layered memory and self-written skills.
- `podcast-generation` [enabled, public]: Use this skill when the user requests to generate, create, or produce podcasts from text content. Converts written content into a two-host conversational podcast audio format with natural dialogue.
- `ppt-generation` [enabled, public]: Use this skill when the user requests to generate, create, or make presentations (PPT/PPTX). Creates visually rich slides by generating images for each slide and composing them into a PowerPoint file.
- `semgrep:scan` [enabled, public]: Run Semgrep security scans before or during security-sensitive coding work, especially changes involving auth, secrets, network access, shell execution, file handling, deserialization, dependencies, or CI/CD workflows.
- `skill-creator` [enabled, public]: Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.
- `smb-cs-playbook` [enabled, public]: Plan-only SMB customer-success playbook: kickoff agenda, 30/60/90 health-check templates, escalation paths, QBR template, churn-save runbook.
- `smb-finance-close` [enabled, public]: Plan-only SMB month-end close playbook: bank recon, accruals, revenue cutoff, expense classification, tax provision check, close packet, audit trail review.
- `smb-hr-onboarding` [enabled, public]: Use this skill when a small or medium business (SMB) user needs to design, run, or audit a new-employee onboarding workflow. The skill produces a structured onboarding plan covering Day −7 → Day 30, including offer-letter checklist, equipment provisioning, accounts/access provisioning, compliance and policy delivery, first-week training agenda, mentor pairing, and Day-30 review. The skill is policy-aware (regional labor law, data-privacy, accessibility) and always produces a draft that requires explicit HR sign-off before any external side effects (sending offer letters, granting accounts, ordering hardware) are executed.
- `smb-it-helpdesk-runbook` [enabled, public]: Plan-only SMB IT helpdesk runbook: ticket triage, priority matrix, password reset SOP, equipment request SOP, access request SOP, escalation paths, SLA definitions.
- `smb-sales-motion` [enabled, public]: Plan-only SMB sales motion playbook: ICP definition, outbound cadence, discovery script, demo template, proposal template, negotiation guardrails, CS handoff packet.
- `spec-kit` [enabled, public]: 'Specification-driven development kit. Generates formal specs, BDD scenarios, acceptance criteria, and API contracts from requirements. USE FOR: writing specs, creating test plans, BDD/Given-When-Then scenarios, acceptance criteria, contract testing, spec-first API design, feature specifications, definition of done checklists. DO NOT USE FOR: one-off tasks without a spec, hotfixes, exploratory work without clear requirements.'
- `surprise-me` [enabled, public]: Create a delightful, unexpected "wow" experience for the user by dynamically discovering and creatively combining other enabled skills. Triggers when the user says "surprise me" or any request expressing a desire for an unexpected creative showcase. Also triggers when the user is bored, wants inspiration, or asks for "something interesting".
- `tokenspeed-benchmark` [enabled, public]: TokenSpeed benchmark planning skill for LLM inference experiments.
- `vercel-deploy` [enabled, public]: Deploy applications and websites to Vercel. Use this skill when the user requests deployment actions such as "Deploy my app", "Deploy this to production", "Create a preview deployment", "Deploy and give me the link", or "Push this live". No authentication required - returns preview URL and claimable deployment link.
- `video-generation` [enabled, public]: Use this skill when the user requests to generate, create, or imagine videos. Supports structured prompts and reference image for guided generation.
- `voltagent-best-practices` [enabled, public]: VoltAgent architectural patterns and conventions. Covers agents vs workflows, project layout, memory, servers, and observability.
- `web-design-guidelines` [enabled, public]: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
- `witr-runtime-diagnosis` [enabled, public]: Runtime diagnosis skill for explaining why processes and services are running.
- `workday-broker` [enabled, public]: Plan-only Workday onboarding broker: produces a signed-intent SOAP/REST envelope for the Hire business process. OctoAgent never calls Workday tenants directly; output is an artifact for a credentialed integration user.

## Plugins

- `agent-rules-skill-pack` [enabled, engineering]: Agent Rules Skill Pack
- `cloakbrowser-controlled-automation` [enabled, integration]: CloakBrowser Controlled Automation
- `compound-engineering-review` [enabled, engineering]: Compound Engineering Review
- `content-experiment-workflow` [enabled, engineering]: Cheat On Content Workflow
- `diagram-generation-toolkit` [enabled, integration]: Fireworks Tech Graph Toolkit
- `goalbuddy-workflow` [enabled, engineering]: Goalbuddy Workflow
- `html-deck-generator` [enabled, integration]: Beautiful HTML Deck Generator
- `ian-handdrawn-ppt` [enabled, integration]: Ian Handdrawn PPT
- `lightseek-smg-gateway` [enabled, runtime]: Lightseek SMG Gateway
- `lumibot-research-strategy` [enabled, integration]: Lumibot Research Strategy
- `mirage-vfs-bridge` [enabled, runtime]: Mirage VFS Bridge
- `peekaboo-vision-mcp` [enabled, integration]: Peekaboo Vision MCP
- `photo-agents-vision-workflow` [enabled, engineering]: Photo Agents Vision Workflow
- `tokenspeed-model-benchmark` [enabled, runtime]: TokenSpeed Model Benchmark
- `witr-runtime-diagnostics` [enabled, runtime]: WITR Runtime Diagnostics
- `workspace-runtime-bridge` [enabled, runtime]: Workspace Runtime Bridge

## Channels

- `feishu` [disabled]: 飞书/Lark IM — WebSocket 实时通道
- `slack` [disabled]: Slack — Socket Mode 实时通道
- `telegram` [disabled]: Telegram Bot — 长轮询通道

## Managed tools
