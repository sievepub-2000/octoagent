"""Workspace blueprint construction helpers."""

from __future__ import annotations

from typing import Any

from src.runtime.config.ml_intern_defaults import build_ml_intern_runtime_context

from .card_templates import TaskCardTemplateFactory
from .contracts import (
    AgentConversationRef,
    AgentHandle,
    AgentMessage,
    DeploymentInterface,
    DockerExecutionProfile,
    TaskCardEdge,
    TaskCardGraph,
    TaskExecutionMode,
    make_id,
    utc_now,
)


class TaskWorkspaceBlueprintFactory:
    """Build default task workspace structures."""

    def __init__(self):
        self._cards = TaskCardTemplateFactory()

    def selected_runtime_profiles(self) -> list[DockerExecutionProfile]:
        return [
            DockerExecutionProfile(
                profile_id="runtime-local-host",
                label="Local Host Sandbox",
                runtime_kind="local_host",
                selected=True,
                capabilities=["workspace_io", "agent_tools", "checkpoints"],
            ),
            DockerExecutionProfile(
                profile_id="runtime-docker-local",
                label="Docker Local Sandbox",
                runtime_kind="docker_local",
                image="octoagent-sandbox:local",
                capabilities=["workspace_io", "container_isolation", "checkpoints"],
            ),
            DockerExecutionProfile(
                profile_id="runtime-docker-provisioner",
                label="Docker Provisioner",
                runtime_kind="docker_provisioner",
                image="octoagent-provisioner:dev",
                live_status="degraded",
                capabilities=["remote_sandbox", "multi_runner"],
            ),
            DockerExecutionProfile(
                profile_id="runtime-desktop-local",
                label="Desktop Local Execution",
                runtime_kind="desktop_local",
                live_status="disabled",
                approval_level="strict",
                capabilities=["snapshot", "audit"],
            ),
        ]

    def default_interfaces(self) -> list[DeploymentInterface]:
        return [
            DeploymentInterface(
                kind="conversation",
                label="Conversation Interface",
                config={"entry": "chat", "thread_binding": "task_scoped"},
            ),
            DeploymentInterface(
                kind="internal",
                label="Internal Task Entry",
                config={"entry": "workspace_task_bar"},
            ),
        ]

    def default_permission_mode(self, mode: TaskExecutionMode) -> str:
        _ = mode
        return "approval"

    def effective_mode_from_builder(
        self,
        fallback_mode: TaskExecutionMode,
        builder_draft: dict[str, Any] | None = None,
    ) -> TaskExecutionMode:
        if isinstance(builder_draft, dict):
            requested_mode = str(builder_draft.get("mode") or "").strip()
            if requested_mode == "branch":
                return "branch"
            if requested_mode == "group":
                return "group"
            if requested_mode == "task":
                return "single"
        return fallback_mode

    def rebuild_agents(
        self,
        task_id: str,
        mode: TaskExecutionMode,
        *,
        current_agents: list[AgentHandle] | None = None,
        builder_draft: dict[str, Any] | None = None,
        auto_research: bool = False,
        enabled_skills: list[str] | None = None,
    ) -> tuple[list[AgentHandle], dict[str, list[AgentMessage]]]:
        effective_mode = self.effective_mode_from_builder(mode, builder_draft)
        blueprints = self._agent_blueprints_for_builder(effective_mode, builder_draft)
        existing_agents = list(current_agents or [])
        used_agent_ids: set[str] = set()
        seed_messages: dict[str, list[AgentMessage]] = {}
        agents: list[AgentHandle] = []
        # Let the runtime select the best configured model; embedded backup
        # is only used as a last-resort fallback *during* execution, not here.
        model_name: str | None = None

        for index, blueprint in enumerate(blueprints):
            matched_agent = self._match_existing_agent(existing_agents, blueprint, used_agent_ids, index)
            agent_id = matched_agent.agent_id if matched_agent is not None else make_id("agent")
            metadata = dict(matched_agent.metadata) if matched_agent is not None else {}
            metadata["auto_research"] = auto_research
            metadata["builder_role"] = blueprint["role"]
            metadata.setdefault("langgraph_assistant_id", "lead_agent")
            metadata.setdefault(
                "langgraph_thread_scope",
                "agent" if effective_mode in {"branch", "group"} else "workspace",
            )
            metadata.setdefault("langgraph_native_runtime", True)
            metadata.update(build_ml_intern_runtime_context("interactive"))
            if enabled_skills:
                metadata["enabled_skills"] = enabled_skills
            else:
                metadata.pop("enabled_skills", None)

            conversation = matched_agent.conversation.model_copy(update={"task_id": task_id, "agent_id": agent_id}) if matched_agent is not None else AgentConversationRef(task_id=task_id, agent_id=agent_id)
            agents.append(
                AgentHandle(
                    agent_id=agent_id,
                    name=blueprint["name"],
                    role=blueprint["role"],
                    status=matched_agent.status if matched_agent is not None else "idle",
                    model_name=matched_agent.model_name if matched_agent is not None else model_name,
                    linked_card_id=None,
                    task_scope=blueprint["scope"],
                    conversation=conversation,
                    metadata=metadata,
                )
            )
            used_agent_ids.add(agent_id)

            if matched_agent is None:
                seed_messages[agent_id] = [
                    AgentMessage(
                        message_id=make_id("message"),
                        role="system",
                        content=f"{blueprint['name']} initialized for task workspace orchestration.",
                        created_at=utc_now(),
                    )
                ]

        return agents, seed_messages

    def make_agents(
        self,
        task_id: str,
        mode: TaskExecutionMode,
        *,
        auto_research: bool = False,
        enabled_skills: list[str] | None = None,
        primary_agent: str | None = None,
        sub_agents: list[str] | None = None,
        agent_runtime_provider: str | None = None,
    ) -> tuple[list[AgentHandle], dict[str, list[AgentMessage]]]:
        # Let the runtime select the best configured model; embedded backup
        # is only used as a last-resort fallback *during* execution, not here.
        model_name: str | None = None
        agents: list[AgentHandle] = []
        seed_messages: dict[str, list[AgentMessage]] = {}

        # Use wizard-provided agents if available, else fallback to blueprints
        if primary_agent or sub_agents:
            blueprints = self._agent_blueprints_from_wizard(mode, primary_agent, sub_agents)
        else:
            blueprints = self._agent_blueprints(mode, agent_runtime_provider=agent_runtime_provider)

        for blueprint in blueprints:
            agent_id = make_id("agent")
            metadata: dict[str, object] = {"auto_research": auto_research}
            metadata["langgraph_assistant_id"] = "lead_agent"
            metadata["langgraph_thread_scope"] = "agent" if mode in {"branch", "group"} else "workspace"
            metadata["langgraph_native_runtime"] = True
            metadata.update(build_ml_intern_runtime_context("interactive"))
            if enabled_skills:
                metadata["enabled_skills"] = enabled_skills
            agents.append(
                AgentHandle(
                    agent_id=agent_id,
                    name=blueprint["name"],
                    role=blueprint["role"],
                    model_name=model_name,
                    task_scope=blueprint["scope"],
                    conversation=AgentConversationRef(task_id=task_id, agent_id=agent_id),
                    metadata=metadata,
                )
            )
            seed_messages[agent_id] = [
                AgentMessage(
                    message_id=make_id("message"),
                    role="system",
                    content=f"{blueprint['name']} initialized for task workspace orchestration.",
                    created_at=utc_now(),
                )
            ]
        return agents, seed_messages

    def build_card_graph(
        self,
        mode: TaskExecutionMode,
        *,
        goal: str,
        agents: list[AgentHandle],
        runtime_profiles: list[DockerExecutionProfile],
        auto_research: bool = False,
        enabled_skills: list[str] | None = None,
        topology: str | None = None,
    ) -> TaskCardGraph:
        # ── Card 1: Project Info ──
        project_id = make_id("card")
        cards = [
            self._cards.create(
                card_id=project_id,
                kind="start",
                title="Project Info",
                description=goal or "Workflow project entry point.",
                config={"goal": goal, "mode": mode, "topology": topology or mode},
                tags=["project", "entry"],
                ui={"variant": "entry", "accent": "task"},
            ),
        ]
        edges: list[TaskCardEdge] = []

        # ── Card 2: Main Agent ──
        main_agent = agents[0] if agents else None
        main_card_id = make_id("card")
        if main_agent:
            main_agent.linked_card_id = main_card_id
            cards.append(
                self._cards.create(
                    card_id=main_card_id,
                    kind="agent",
                    title=main_agent.name,
                    description=main_agent.task_scope,
                    linked_agent_id=main_agent.agent_id,
                    config={"role": main_agent.role, "model_name": main_agent.model_name, "is_primary": True},
                    tags=["agent", "primary"],
                    ui={"variant": "agent", "role": main_agent.role, "is_primary": True},
                )
            )
            edges.append(
                TaskCardEdge(
                    edge_id=make_id("edge"),
                    source_card_id=project_id,
                    target_card_id=main_card_id,
                    label="orchestrates",
                )
            )

        # ── Sub-agent cards (card 3+) ──
        sub_agents = agents[1:]
        effective_topology = topology or mode

        if effective_topology == "branch" and sub_agents:
            # Branch: main → each sub-agent (tree/fan-out)
            for sub_agent in sub_agents:
                sub_card_id = make_id("card")
                sub_agent.linked_card_id = sub_card_id
                cards.append(
                    self._cards.create(
                        card_id=sub_card_id,
                        kind="agent",
                        title=sub_agent.name,
                        description=sub_agent.task_scope,
                        linked_agent_id=sub_agent.agent_id,
                        config={"role": sub_agent.role, "model_name": sub_agent.model_name},
                        tags=["agent", "sub-agent"],
                        ui={"variant": "agent", "role": sub_agent.role},
                    )
                )
                edges.append(
                    TaskCardEdge(
                        edge_id=make_id("edge"),
                        source_card_id=main_card_id,
                        target_card_id=sub_card_id,
                        label="dispatches",
                    )
                )
                # Return edge (sub → main for reporting)
                edges.append(
                    TaskCardEdge(
                        edge_id=make_id("edge"),
                        source_card_id=sub_card_id,
                        target_card_id=main_card_id,
                        label="reports",
                    )
                )

        elif effective_topology == "group" and sub_agents:
            # Group/Swarm: all agents interconnected bidirectionally
            all_agent_cards = [(main_card_id, main_agent)]
            for sub_agent in sub_agents:
                sub_card_id = make_id("card")
                sub_agent.linked_card_id = sub_card_id
                cards.append(
                    self._cards.create(
                        card_id=sub_card_id,
                        kind="agent",
                        title=sub_agent.name,
                        description=sub_agent.task_scope,
                        linked_agent_id=sub_agent.agent_id,
                        config={"role": sub_agent.role, "model_name": sub_agent.model_name},
                        tags=["agent", "sub-agent"],
                        ui={"variant": "agent", "role": sub_agent.role},
                    )
                )
                all_agent_cards.append((sub_card_id, sub_agent))
                # Bidirectional with main (dispatch + report)
                edges.append(
                    TaskCardEdge(
                        edge_id=make_id("edge"),
                        source_card_id=main_card_id,
                        target_card_id=sub_card_id,
                        label="dispatches",
                    )
                )
                edges.append(
                    TaskCardEdge(
                        edge_id=make_id("edge"),
                        source_card_id=sub_card_id,
                        target_card_id=main_card_id,
                        label="reports",
                    )
                )
            # Inter-sub-agent links (for swarm communication)
            for i, (cid_a, _) in enumerate(all_agent_cards[1:], 1):
                for cid_b, _ in all_agent_cards[i + 1 :]:
                    edges.append(
                        TaskCardEdge(
                            edge_id=make_id("edge"),
                            source_card_id=cid_a,
                            target_card_id=cid_b,
                            label="collaborates",
                        )
                    )
                    edges.append(
                        TaskCardEdge(
                            edge_id=make_id("edge"),
                            source_card_id=cid_b,
                            target_card_id=cid_a,
                            label="collaborates",
                        )
                    )

        else:
            # Single / chain: main agent only (or main → sub1 → sub2 chain)
            previous_id = main_card_id
            for sub_agent in sub_agents:
                sub_card_id = make_id("card")
                sub_agent.linked_card_id = sub_card_id
                cards.append(
                    self._cards.create(
                        card_id=sub_card_id,
                        kind="agent",
                        title=sub_agent.name,
                        description=sub_agent.task_scope,
                        linked_agent_id=sub_agent.agent_id,
                        config={"role": sub_agent.role, "model_name": sub_agent.model_name},
                        tags=["agent", "sub-agent"],
                        ui={"variant": "agent", "role": sub_agent.role},
                    )
                )
                edges.append(
                    TaskCardEdge(
                        edge_id=make_id("edge"),
                        source_card_id=previous_id,
                        target_card_id=sub_card_id,
                        label="chain",
                    )
                )
                previous_id = sub_card_id

        return TaskCardGraph(cards=cards, edges=edges)

    def _agent_blueprints(
        self,
        mode: TaskExecutionMode,
        *,
        agent_runtime_provider: str | None = None,
    ) -> list[dict[str, Any]]:
        _ = agent_runtime_provider
        return self._langgraph_blueprints(mode)

    # ── Provider-specific blueprint sets ──

    @staticmethod
    def _langgraph_blueprints(mode: TaskExecutionMode) -> list[dict[str, Any]]:
        if mode == "branch":
            return [
                {"name": "Lead Coordinator", "role": "coordinator", "scope": "Task coordination"},
                {"name": "Research Worker", "role": "researcher", "scope": "Research branch"},
                {"name": "Builder Worker", "role": "builder", "scope": "Implementation branch"},
                {"name": "Review Agent", "role": "reviewer", "scope": "Cross-branch review"},
            ]
        if mode == "group":
            return [
                {"name": "Group Manager", "role": "manager", "scope": "Group coordination"},
                {"name": "Research Worker", "role": "researcher", "scope": "Research"},
                {"name": "Coder Worker", "role": "coder", "scope": "Execution"},
                {"name": "Reviewer Agent", "role": "reviewer", "scope": "Review"},
            ]
        return [{"name": "Lead Agent", "role": "lead", "scope": "Single-chain execution"}]

    def _agent_blueprints_for_builder(
        self,
        mode: TaskExecutionMode,
        builder_draft: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        if not isinstance(builder_draft, dict):
            return self._agent_blueprints(mode)

        sequence = self._builder_agent_sequence(mode, builder_draft)
        if not sequence:
            return self._agent_blueprints(mode)

        branch_scopes = self._branch_scope_map(builder_draft)
        collaboration_style = str(builder_draft.get("collaborationStyle") or "").strip()
        return [
            self._builder_agent_blueprint(
                token,
                mode,
                branch_scope=branch_scopes.get(self._normalize_agent_token(token)),
                collaboration_style=collaboration_style,
            )
            for token in sequence
        ]

    def _builder_agent_sequence(
        self,
        mode: TaskExecutionMode,
        builder_draft: dict[str, Any],
    ) -> list[str]:
        ordered_tokens: list[str] = []
        seen: set[str] = set()

        def add_token(value: str) -> None:
            normalized = self._normalize_agent_token(value)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            ordered_tokens.append(normalized)

        route = builder_draft.get("route")
        if isinstance(route, list):
            for item in route:
                if isinstance(item, str):
                    add_token(item)

        agents = builder_draft.get("agents")
        if isinstance(agents, list):
            for item in agents:
                if isinstance(item, str):
                    add_token(item)

        branches = builder_draft.get("branches")
        if isinstance(branches, list):
            for item in branches:
                if isinstance(item, dict) and isinstance(item.get("agentName"), str):
                    add_token(str(item["agentName"]))

        preferred_primary = "group_manager" if mode == "group" else "lead_agent"
        if preferred_primary in seen:
            ordered_tokens = [preferred_primary, *[item for item in ordered_tokens if item != preferred_primary]]
        elif "lead_agent" in seen:
            ordered_tokens = ["lead_agent", *[item for item in ordered_tokens if item != "lead_agent"]]
        elif ordered_tokens:
            ordered_tokens.insert(0, preferred_primary)
        else:
            ordered_tokens.append(preferred_primary)

        return ordered_tokens

    def _branch_scope_map(self, builder_draft: dict[str, Any]) -> dict[str, str]:
        branches = builder_draft.get("branches")
        if not isinstance(branches, list):
            return {}
        scope_map: dict[str, str] = {}
        for item in branches:
            if not isinstance(item, dict):
                continue
            agent_name = item.get("agentName")
            responsibility = item.get("responsibility")
            if isinstance(agent_name, str) and isinstance(responsibility, str) and responsibility.strip():
                scope_map[self._normalize_agent_token(agent_name)] = responsibility.strip()
        return scope_map

    def _builder_agent_blueprint(
        self,
        token: str,
        mode: TaskExecutionMode,
        *,
        branch_scope: str | None,
        collaboration_style: str,
    ) -> dict[str, Any]:
        normalized = self._normalize_agent_token(token)
        primary_role = "manager" if mode == "group" else "coordinator" if mode == "branch" else "lead"
        defaults: dict[str, dict[str, str]] = {
            "lead_agent": {
                "name": "Group Manager" if mode == "group" else "Lead Coordinator" if mode == "branch" else "Lead Agent",
                "role": primary_role,
                "scope": "Group coordination" if mode == "group" else "Task coordination" if mode == "branch" else "Single-chain execution",
            },
            "group_manager": {
                "name": "Group Manager",
                "role": "manager",
                "scope": "Group coordination",
            },
            "researcher": {
                "name": "Research Worker",
                "role": "researcher",
                "scope": branch_scope or "Research branch",
            },
            "coder": {
                "name": "Builder Worker",
                "role": "coder",
                "scope": branch_scope or "Implementation branch",
            },
            "builder": {
                "name": "Builder Worker",
                "role": "builder",
                "scope": branch_scope or "Implementation branch",
            },
            "executor": {
                "name": "Execution Worker",
                "role": "executor",
                "scope": branch_scope or "Task execution",
            },
            "reviewer": {
                "name": "Review Agent",
                "role": "reviewer",
                "scope": branch_scope or ("Deep review" if collaboration_style == "deep_review" else "Cross-branch review"),
            },
            "policy_reviewer": {
                "name": "Policy Reviewer",
                "role": "policy_reviewer",
                "scope": branch_scope or "Policy and guardrail review",
            },
        }
        if normalized in defaults:
            return defaults[normalized]
        display_name = self._titleize_agent_token(normalized)
        return {
            "name": display_name,
            "role": normalized,
            "scope": branch_scope or f"{display_name} task",
        }

    def _match_existing_agent(
        self,
        existing_agents: list[AgentHandle],
        blueprint: dict[str, Any],
        used_agent_ids: set[str],
        preferred_index: int,
    ) -> AgentHandle | None:
        expected_name = self._normalize_agent_token(str(blueprint.get("name") or ""))
        expected_role = self._normalize_agent_token(str(blueprint.get("role") or ""))
        expected_scope = self._normalize_agent_token(str(blueprint.get("scope") or ""))
        best_match: AgentHandle | None = None
        best_score = -1

        for index, agent in enumerate(existing_agents):
            if agent.agent_id in used_agent_ids:
                continue
            score = 0
            if self._normalize_agent_token(agent.name) == expected_name:
                score += 40
            if self._normalize_agent_token(agent.role) == expected_role:
                score += 60
            if expected_scope and self._normalize_agent_token(agent.task_scope or "") == expected_scope:
                score += 10
            if index == preferred_index:
                score += 5
            if score > best_score:
                best_match = agent
                best_score = score

        return best_match if best_score > 0 else None

    @staticmethod
    def _normalize_agent_token(value: str) -> str:
        return value.strip().lower().replace(" ", "_").replace("-", "_")

    @staticmethod
    def _titleize_agent_token(value: str) -> str:
        return " ".join(part.capitalize() for part in value.split("_") if part)

    def _agent_blueprints_from_wizard(
        self,
        mode: TaskExecutionMode,
        primary_agent: str | None,
        sub_agents: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Build agent blueprints from wizard-provided agent names."""
        primary_name = primary_agent or "Lead Agent"
        primary_role = "coordinator" if mode in ("branch", "group") else "lead"
        primary_scope = "Planning, dispatching, supervising, and reporting" if mode in ("branch", "group") else "Single-chain execution"
        blueprints: list[dict[str, Any]] = [
            {"name": primary_name, "role": primary_role, "scope": primary_scope},
        ]
        for agent_name in sub_agents or []:
            blueprints.append(
                {
                    "name": agent_name,
                    "role": "sub-agent",
                    "scope": f"Sub-agent task (assigned by {primary_name})",
                }
            )
        return blueprints
