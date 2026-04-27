"""Session profile assembly helpers for query engine."""

from __future__ import annotations

from pathlib import Path

from src.agent_core.roles import has_reviewer_agent
from src.ml_intern_defaults import ML_INTERN_HF_MCP_SERVER, build_ml_intern_runtime_context, resolve_ml_intern_profile_name

from .contracts import (
    PromptSection,
    QueryContextSnapshot,
    QueryMcpServerSummary,
    QueryMemoryLayer,
    QueryMemoryProfile,
    QuerySession,
    QuerySessionSummary,
    QueryTaskAnalysis,
    QueryToolDescriptor,
)


class QuerySessionProfileAssembler:
    """Build context, memory, tool, and prompt sections for query sessions."""

    def __init__(self, make_id, append_event, *, get_memory_data_fn, extensions_config_cls, get_paths_fn):
        self._make_id = make_id
        self._append_event = append_event
        self._get_memory_data = get_memory_data_fn
        self._extensions_config_cls = extensions_config_cls
        self._get_paths = get_paths_fn

    def build_previous_summary_section(self, previous_summary: QuerySessionSummary) -> PromptSection:
        return PromptSection(
            section_id=f"previous-summary-{previous_summary.summary_id}",
            title="Previous Session Summary",
            content=previous_summary.content,
            cache_behavior="dynamic",
        )

    def build_memory_layers(
        self,
        workspace,
        previous_summary: QuerySessionSummary | None,
        *,
        session_id: str,
    ) -> list[QueryMemoryLayer]:
        layers = [
            self._build_session_memory_layer(previous_summary),
            self._build_workspace_memory_layer(workspace, session_id=session_id),
            self._build_project_memory_layer(session_id=session_id),
        ]
        return [layer for layer in layers if layer is not None]

    def update_memory_profile(self, session: QuerySession) -> None:
        archived_turn_count = int(session.metadata.get("archived_turn_count", 0))
        compaction_count = len(session.summaries)
        total_turns = len(session.turns) + archived_turn_count
        prompt_weight = max(1, len(session.assembled_system_prompt) // 4000)
        memory_layers = list(session.memory_layers)
        weighted_signal_score = round(sum(layer.weight for layer in memory_layers), 2)
        scope_weights: dict[str, float] = {}
        for layer in memory_layers:
            scope_weights[layer.scope] = scope_weights.get(layer.scope, 0.0) + layer.weight
        dominant_scope = "mixed"
        if scope_weights:
            ranked_scopes = sorted(scope_weights.items(), key=lambda item: item[1], reverse=True)
            if len(ranked_scopes) == 1 or (
                len(ranked_scopes) > 1 and abs(ranked_scopes[0][1] - ranked_scopes[1][1]) >= 0.1
            ):
                dominant_scope = ranked_scopes[0][0]
        recall_summary = " | ".join(self.truncate_text(layer.summary, limit=120) for layer in memory_layers[:2])
        pressure_score = total_turns + prompt_weight + compaction_count + max(0, len(memory_layers) - 1)
        if pressure_score >= 12:
            context_pressure = "high"
            recommended_action = "compact"
        elif pressure_score >= 6:
            context_pressure = "medium"
            recommended_action = "refresh"
        else:
            context_pressure = "low"
            recommended_action = "continue"
        session.memory_profile = QueryMemoryProfile(
            archived_turn_count=archived_turn_count,
            compaction_count=compaction_count,
            active_layers=len(memory_layers),
            dominant_scope=dominant_scope,
            weighted_signal_score=weighted_signal_score,
            recall_summary=recall_summary,
            context_pressure=context_pressure,
            recommended_action=recommended_action,
        )

    def refresh_session_profile(
        self,
        session: QuerySession,
        workspace,
        agent,
        prompt_stack,
        *,
        created_at: str,
        reason: str,
        previous_summary: QuerySessionSummary | None,
        permission_mode_resolver,
    ) -> None:
        permission_mode = permission_mode_resolver(workspace, agent)
        session.context_snapshot = self.build_context_snapshot(workspace, session_id=session.session_id)
        session.mcp_servers = self.build_mcp_servers()
        session.available_tools = self.build_tool_registry(
            workspace,
            session.mcp_servers,
            permission_mode=permission_mode,
        )
        session.task_analysis = self.build_task_analysis(
            workspace,
            agent,
            prompt_stack,
            session_id=session.session_id,
            permission_mode=permission_mode,
        )
        session.memory_layers = self.build_memory_layers(workspace, previous_summary, session_id=session.session_id)
        session.metadata["permission_mode"] = permission_mode
        ml_intern_context = build_ml_intern_runtime_context(
            permission_mode=permission_mode,
            workflow_run_mode=getattr(workspace, "metadata", {}).get("workflow_run_mode"),
        )
        session.metadata.update(ml_intern_context)
        session.metadata["memory_layer_count"] = len(session.memory_layers)
        session.metadata["memory_layer_scopes"] = [layer.scope for layer in session.memory_layers]
        session.prompt_sections = [
            PromptSection(
                section_id=module.module_id,
                title=module.title,
                content=self.render_module_content(
                    module,
                    session=session,
                    workspace=workspace,
                    agent=agent,
                    context_snapshot=session.context_snapshot,
                    tool_registry=session.available_tools,
                    mcp_servers=session.mcp_servers,
                    task_analysis=session.task_analysis,
                    previous_summary=previous_summary,
                ),
                cache_behavior="dynamic" if module.stage in {"reminder", "routing", "summarization"} else "stable",
            )
            for module in prompt_stack.modules
        ]
        if previous_summary is not None:
            session.prompt_sections.append(self.build_previous_summary_section(previous_summary))
        session.assembled_system_prompt = self.assemble_system_prompt(session.prompt_sections)
        session.updated_at = created_at
        self._append_event(
            session,
            kind="context_snapshot_built",
            detail=f"Context snapshot refreshed for reason '{reason}'.",
            created_at=created_at,
        )
        self._append_event(
            session,
            kind="tool_registry_built",
            detail=f"Tool registry rebuilt with {len(session.available_tools)} tools and {len(session.mcp_servers)} MCP servers.",
            created_at=created_at,
        )
        self._append_event(
            session,
            kind="task_analyzed",
            detail="Task analysis refreshed from workspace cards, runtimes, and prompt stack.",
            created_at=created_at,
        )
        self.update_memory_profile(session)

    def build_context_snapshot(self, workspace, *, session_id: str) -> QueryContextSnapshot:
        selected_runtime_profiles = [profile.label for profile in workspace.runtime_profiles if profile.selected]
        deployment_interfaces = [item.label for item in workspace.deployment_interfaces if item.enabled]
        return QueryContextSnapshot(
            snapshot_id=f"context-snapshot-{session_id}",
            repo_root=self.repo_root(),
            workspace_mode=workspace.mode,
            active_goal=workspace.goal or workspace.summary or workspace.name,
            top_docs=self.candidate_top_docs(),
            selected_runtime_profiles=selected_runtime_profiles,
            deployment_interfaces=deployment_interfaces,
            compiled_graph_id=workspace.metadata.get("compiled_graph_id"),
            card_count=len(workspace.card_graph.cards),
            checkpoint_count=len(workspace.checkpoints),
            agent_count=len(workspace.agents),
        )

    def build_mcp_servers(self) -> list[QueryMcpServerSummary]:
        extensions_config = self._extensions_config_cls.from_file()
        servers = [
            QueryMcpServerSummary(
                server_id=name,
                transport=(config.type if config.type in {"stdio", "sse", "http"} else "stdio"),
                enabled=config.enabled,
                description=config.description,
                auth_mode="oauth" if config.oauth is not None else "none",
            )
            for name, config in extensions_config.get_enabled_mcp_servers().items()
        ]
        if not any(server.server_id == "hf-mcp-server" for server in servers):
            servers.append(
                QueryMcpServerSummary(
                    server_id="hf-mcp-server",
                    transport=ML_INTERN_HF_MCP_SERVER["transport"],
                    enabled=True,
                    description="Hugging Face MCP server from ml-intern default profile.",
                    auth_mode="oauth",
                )
            )
        return servers

    def build_tool_registry(
        self,
        workspace,
        mcp_servers: list[QueryMcpServerSummary],
        *,
        permission_mode: str,
    ) -> list[QueryToolDescriptor]:
        workspace_approval = permission_mode not in {"workspace", "system", "yolo"}
        system_approval = permission_mode not in {"workspace", "system", "yolo"}
        browser_approval = permission_mode not in {"system", "yolo"}
        tools = [
            QueryToolDescriptor(
                tool_id="repo-read",
                title="Repository Read Tools",
                source="builtin",
                kind="read",
                enabled=True,
                requires_approval=False,
                note="Read repo files, grep, glob, and inspect git status for project analysis.",
            ),
            QueryToolDescriptor(
                tool_id="repo-write",
                title="Repository Write Tools",
                source="builtin",
                kind="write",
                enabled=True,
                requires_approval=workspace_approval,
                note="Modify repository files through the shared engineering workflow.",
            ),
            QueryToolDescriptor(
                tool_id="shell-exec",
                title="Shell Execution",
                source="builtin",
                kind="exec",
                enabled=True,
                requires_approval=system_approval,
                note="Run bounded shell commands under the system execution permission model.",
            ),
            QueryToolDescriptor(
                tool_id="browser-runtime",
                title="Browser Runtime",
                source="builtin",
                kind="browser",
                enabled=True,
                requires_approval=browser_approval,
                note="Operate the shared browser runtime used by both embedded desktop and browser WebUI modes.",
            ),
            QueryToolDescriptor(
                tool_id="system-execution",
                title="System Execution",
                source="builtin",
                kind="system",
                enabled=True,
                requires_approval=system_approval,
                note="Execute bounded system-level actions using the shared session and audit contracts.",
            ),
            QueryToolDescriptor(
                tool_id="research-runtime",
                title="Research Runtime",
                source="builtin",
                kind="research",
                enabled=True,
                requires_approval=False,
                note="Run bounded experiment loops within the current project workspace.",
            ),
            QueryToolDescriptor(
                tool_id="task-workspace",
                title="Task Workspace Coordination",
                source="builtin",
                kind="coordination",
                enabled=True,
                requires_approval=False,
                note="Compile plans, manage cards, checkpoints, and handoffs inside the current task workspace.",
            ),
        ]
        for server in mcp_servers:
            tools.append(
                QueryToolDescriptor(
                    tool_id=f"mcp-{server.server_id}",
                    title=f"MCP Server: {server.server_id}",
                    source="mcp",
                    kind="integration",
                    enabled=server.enabled,
                    requires_approval=server.auth_mode == "oauth",
                    note=server.description or f"MCP integration via {server.transport}.",
                )
            )
        if workspace.metadata.get("research_experiment_id"):
            tools.append(
                QueryToolDescriptor(
                    tool_id="workspace-research-bindings",
                    title="Workspace Research Bindings",
                    source="builtin",
                    kind="research",
                    enabled=True,
                    requires_approval=False,
                    note="Workspace already has an attached research experiment and can resume trial work directly.",
                )
            )
        for plugin_id in workspace.metadata.get("active_plugin_ids", []):
            tools.append(
                QueryToolDescriptor(
                    tool_id=f"plugin-{plugin_id}",
                    title=f"Plugin: {plugin_id}",
                    source="plugin",
                    kind="integration",
                    enabled=True,
                    requires_approval=False,
                    note=f"Workspace plugin '{plugin_id}' is active for the current coordination flow.",
                )
            )
        return tools

    def build_task_analysis(
        self,
        workspace,
        agent,
        prompt_stack,
        *,
        session_id: str,
        permission_mode: str,
    ) -> QueryTaskAnalysis:
        session_mode = str(workspace.metadata.get("session_mode") or ("coordinator" if workspace.mode in {"branch", "group"} else "normal"))
        coordination_strategy = str(
            workspace.metadata.get("coordination_strategy")
            or ("coordinator_workers" if workspace.mode == "branch" else ("manager_review" if workspace.mode == "group" else "solo"))
        )
        flow = [
            "Assemble repository context, active docs, and workspace state.",
            f"Load prompt stack '{prompt_stack.profile_id}' with modular sections.",
            "Load working memory from summaries, plan items, and checkpoints before deeper execution.",
            "Inspect built-in tools, MCP integrations, and approval-sensitive capabilities.",
            f"Apply ML-intern profile {resolve_ml_intern_profile_name(permission_mode=permission_mode, workflow_run_mode=workspace.metadata.get('workflow_run_mode'))} for the current workflow mode.",
            "Review compiled cards, coordinator/reviewer roles, and select the next executable runtime target.",
            "Execute bounded turns, self-review the outcome, then compact or hand off when context pressure increases.",
        ]
        plan_items = list(workspace.metadata.get("plan_items") or []) or [card.title for card in workspace.card_graph.cards[:6]]
        open_questions: list[str] = []
        if not workspace.goal:
            open_questions.append("Workspace goal is still sparse; clarify the operator objective before side effects.")
        if not workspace.metadata.get("compiled_graph_id"):
            open_questions.append("Task graph has not been compiled yet; compile before deep execution.")
        if not workspace.card_graph.cards:
            open_questions.append("Card graph is empty; determine whether this task should stay conversational or be card-driven.")
        suggested_runtime_targets = sorted(
            {
                "query_engine",
                *(card.kind for card in workspace.card_graph.cards if card.kind in {"agent", "tooling", "research", "review"}),
                *(profile.runtime_kind for profile in workspace.runtime_profiles if profile.selected),
            }
        )
        risk_labels: list[str] = []
        if any(card.kind == "research" for card in workspace.card_graph.cards):
            risk_labels.append("research-runtime")
        if any(card.kind == "tooling" for card in workspace.card_graph.cards):
            risk_labels.append("tool-write")
        if any(interface.kind == "api" for interface in workspace.deployment_interfaces):
            risk_labels.append("api-side-effects")
        if has_reviewer_agent(list(workspace.agents)):
            risk_labels.append("review-gated")
        if not risk_labels:
            risk_labels.append("read-mostly")
        review_required = any(label in {"tool-write", "api-side-effects", "review-gated"} for label in risk_labels) or workspace.mode in {"branch", "group"}
        self_review_checklist = [
            "Confirm the result matches the active user goal.",
            "Check whether any changed or inspected surfaces imply follow-up verification.",
            "Record blockers, open questions, or runtime handoffs explicitly.",
        ]
        if review_required:
            self_review_checklist.append("Escalate to a review path before claiming final completion.")
        if permission_mode == "workspace":
            self_review_checklist.append("Stay scoped to workspace operations unless the operator raises the card permission mode.")
        elif permission_mode == "system":
            self_review_checklist.append("System-level execution is permitted; keep actions bounded and auditable.")
        else:
            self_review_checklist.append("YOLO mode is active; execute directly and report concrete results without approval prompts.")
        return QueryTaskAnalysis(
            analysis_id=f"task-analysis-{session_id}",
            summary=(
                f"Agent '{agent.name}' is preparing to work on '{workspace.name}' using a repository-owned "
                "prompt stack, shared tool registry, and bounded handoff workflow."
            ),
            session_mode=session_mode if session_mode in {"normal", "coordinator", "auto"} else "normal",
            coordination_strategy=coordination_strategy if coordination_strategy in {"solo", "coordinator_workers", "manager_review"} else "solo",
            permission_mode=permission_mode,
            execution_flow=flow,
            plan_items=plan_items,
            open_questions=open_questions,
            suggested_runtime_targets=suggested_runtime_targets,
            primary_risk_labels=risk_labels,
            memory_sources=[
                "workspace goal",
                "compiled card graph",
                "checkpoints",
                "session summaries",
                "workspace memory digest",
                "project memory file",
            ],
            self_review_checklist=self_review_checklist,
            review_required=review_required,
        )

    def render_module_content(
        self,
        module,
        *,
        session: QuerySession,
        workspace,
        agent,
        context_snapshot: QueryContextSnapshot,
        tool_registry: list[QueryToolDescriptor],
        mcp_servers: list[QueryMcpServerSummary],
        task_analysis: QueryTaskAnalysis,
        previous_summary: QuerySessionSummary | None,
    ) -> str:
        tool_lines = [
            f"{tool.title} [{tool.kind}] approval={'yes' if tool.requires_approval else 'no'}"
            for tool in tool_registry
            if tool.enabled
        ]
        mcp_lines = [
            f"{server.server_id} via {server.transport} auth={server.auth_mode}"
            for server in mcp_servers
            if server.enabled
        ]
        parts = [module.instruction_template.strip()]
        if module.module_id == "identity":
            parts.extend([f"Current task: {workspace.name}", f"Agent role: {agent.role}", f"Execution mode: {workspace.mode}"])
        elif module.module_id == "workflow":
            parts.extend([f"Goal: {context_snapshot.active_goal}", "Suggested execution flow:", self.format_lines(task_analysis.execution_flow)])
        elif module.module_id == "context_snapshot":
            parts.extend([
                f"Repository root: {context_snapshot.repo_root}",
                "Active docs:",
                self.format_lines(context_snapshot.top_docs),
                f"Compiled graph: {context_snapshot.compiled_graph_id or 'not compiled'}",
                f"Runtime profiles: {', '.join(context_snapshot.selected_runtime_profiles) or 'none selected'}",
            ])
        elif module.module_id == "reminder_start":
            parts.extend(["Enabled tools:", self.format_lines(tool_lines)])
        elif module.module_id == "reminder_end":
            parts.extend(["Open questions:", self.format_lines(task_analysis.open_questions)])
        elif module.module_id == "topic_router":
            parts.extend(["Suggested runtime targets:", self.format_lines(task_analysis.suggested_runtime_targets)])
        elif module.module_id == "compact":
            parts.extend([f"Compaction count: {len(session.summaries)}", "Compact when repeated history no longer changes the next action."])
        elif module.module_id == "summarize_previous":
            parts.append(previous_summary.content if previous_summary is not None else "No previous-session summary is available for this agent.")
        elif module.module_id == "permission_policy":
            parts.extend([
                f"Agent permission mode: {task_analysis.permission_mode}",
                "Primary risk labels:",
                self.format_lines(task_analysis.primary_risk_labels),
                "Available MCP servers:",
                self.format_lines(mcp_lines),
            ])
        elif module.module_id == "working_memory":
            parts.extend([
                "Active plan items:",
                self.format_lines(task_analysis.plan_items),
                "Memory sources:",
                self.format_lines(task_analysis.memory_sources),
                "Weighted memory layers:",
                self.format_lines([f"{layer.scope} weight={layer.weight}: {self.truncate_text(layer.summary, limit=140)}" for layer in session.memory_layers]),
            ])
        elif module.module_id == "self_review":
            parts.extend([f"Review required: {'yes' if task_analysis.review_required else 'no'}", "Self-review checklist:", self.format_lines(task_analysis.self_review_checklist)])
        elif module.module_id == "coordinator_mode":
            parts.extend([
                f"Session mode: {task_analysis.session_mode}",
                f"Coordination strategy: {task_analysis.coordination_strategy}",
                "Agent roster:",
                self.format_lines([f"{item.name} ({item.role})" for item in workspace.agents]),
            ])
        elif module.module_id == "model_routing":
            parts.extend([
                f"Context pressure: {session.memory_profile.context_pressure}",
                f"Recommended action: {session.memory_profile.recommended_action}",
                "Prefer the smallest adequate model path for the current turn.",
            ])
        return "\n".join(part for part in parts if part)

    def assemble_system_prompt(self, sections: list[PromptSection]) -> str:
        return "\n\n".join(f"[{section.title}]\n{section.content}" for section in sections)

    def truncate_text(self, text: str, *, limit: int = 280) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

    def format_lines(self, items: list[str], *, fallback: str = "none") -> str:
        if not items:
            return fallback
        return "\n".join(f"- {item}" for item in items)

    def repo_root(self) -> str:
        return str(self._get_paths().base_dir.resolve())

    def candidate_top_docs(self) -> list[str]:
        repo_root = Path(self.repo_root())
        candidates = [
            repo_root / "README.md",
            repo_root / "docs" / "PLATFORM_BASELINE.md",
            repo_root / "docs" / "ARCHITECTURE_AND_RUNTIME.md",
            repo_root / "docs" / "ROADMAP_AND_PROGRESS.md",
            repo_root / "docs" / "PLATFORM_REFACTOR_BLUEPRINT.md",
        ]
        return [str(path.relative_to(repo_root)) for path in candidates if path.exists()]

    def _build_session_memory_layer(self, previous_summary: QuerySessionSummary | None) -> QueryMemoryLayer | None:
        if previous_summary is None or not previous_summary.content.strip():
            return None
        return QueryMemoryLayer(
            layer_id=f"memory-session-{previous_summary.summary_id}",
            scope="session",
            weight=1.0,
            summary=self.truncate_text(previous_summary.content, limit=320),
            source_refs=[previous_summary.summary_id, *previous_summary.open_items[:3]],
            updated_at=previous_summary.created_at,
        )

    def _build_workspace_memory_layer(self, workspace, *, session_id: str) -> QueryMemoryLayer | None:
        parts: list[str] = []
        source_refs: list[str] = []
        goal = workspace.goal or workspace.summary or workspace.name
        if goal:
            parts.append(f"Goal: {goal}")
            source_refs.append("workspace.goal")
        digest = str(workspace.metadata.get("project_memory_digest") or "").strip()
        if digest:
            parts.append(f"Digest: {digest}")
            source_refs.append("workspace.metadata.project_memory_digest")
        brain_plan_summary = str(workspace.metadata.get("brain_plan_summary") or "").strip()
        if brain_plan_summary:
            parts.append(f"Brain plan: {brain_plan_summary}")
            source_refs.append("workspace.metadata.brain_plan_summary")
        plan_items = list(workspace.metadata.get("plan_items") or [])[:4]
        if plan_items:
            parts.append("Plan items: " + "; ".join(plan_items))
            source_refs.append("workspace.metadata.plan_items")
        checkpoint_labels = [checkpoint.label for checkpoint in workspace.checkpoints[:3]]
        if checkpoint_labels:
            parts.append("Checkpoints: " + "; ".join(checkpoint_labels))
            source_refs.append("workspace.checkpoints")
        last_result = str(workspace.metadata.get("last_agent_result_summary") or "").strip()
        if last_result:
            parts.append(f"Last result: {last_result}")
            source_refs.append("workspace.metadata.last_agent_result_summary")
        if not parts:
            return None
        return QueryMemoryLayer(
            layer_id=f"memory-workspace-{session_id}",
            scope="workspace",
            weight=0.85,
            summary=self.truncate_text(" ".join(parts), limit=360),
            source_refs=source_refs,
            updated_at=workspace.updated_at,
        )

    def _build_project_memory_layer(self, *, session_id: str) -> QueryMemoryLayer | None:
        try:
            memory_data = self._get_memory_data()
        except Exception:
            memory_data = {}
        if not memory_data:
            return None
        user_sections = memory_data.get("user", {})
        history_sections = memory_data.get("history", {})
        if not isinstance(user_sections, dict):
            user_sections = {}
        if isinstance(history_sections, dict):
            history_map = history_sections
        elif isinstance(history_sections, list):
            history_map = {"entries": {"summary": "; ".join(str(item).strip() for item in history_sections if str(item).strip())}}
        else:
            history_map = {}
        raw_facts = memory_data.get("facts", [])
        facts = sorted([fact for fact in raw_facts if isinstance(fact, dict)], key=lambda item: item.get("confidence", 0), reverse=True)
        parts: list[str] = []
        source_refs: list[str] = []
        for section_name in ["workContext", "topOfMind"]:
            section = user_sections.get(section_name, {})
            summary = str(section.get("summary", "")).strip() if isinstance(section, dict) else str(section).strip()
            if summary:
                parts.append(f"{section_name}: {summary}")
                source_refs.append(f"memory.user.{section_name}")
        for section_name in ["recentMonths", "longTermBackground", "entries"]:
            section = history_map.get(section_name, {})
            summary = str(section.get("summary", "")).strip() if isinstance(section, dict) else str(section).strip()
            if summary:
                parts.append(f"{section_name}: {summary}")
                source_refs.append(f"memory.history.{section_name}")
        top_facts = [fact.get("content", "").strip() for fact in facts[:3] if fact.get("content")]
        if top_facts:
            parts.append("Facts: " + "; ".join(top_facts))
            source_refs.append("memory.facts")
        if not parts:
            return None
        weight = 0.6 if not facts else min(0.85, 0.55 + max(float(facts[0].get("confidence", 0)), 0.0) * 0.3)
        return QueryMemoryLayer(
            layer_id=f"memory-project-{session_id}",
            scope="project",
            weight=round(weight, 2),
            summary=self.truncate_text(" ".join(parts), limit=360),
            source_refs=source_refs,
            updated_at=str(memory_data.get("lastUpdated") or ""),
        )
