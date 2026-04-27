"""Workspace plan compilation helpers."""

from __future__ import annotations

import re

from src.agent_core.roles import is_management_role, is_reviewer_role, select_lead_agent, select_reviewer_agent
from src.brain import BrainTaskContext
from src.orchestration import CompiledTaskGraph

from .card_templates import TaskCardTemplateFactory
from .contracts import TaskCard, TaskCardEdge, TaskCardGraph, TaskWorkspace, make_id, utc_now
from .workflow_files import CANONICAL_PROJECT_DOC, CANONICAL_RESULT_DOC, CANONICAL_SETTINGS_DOC

_TOKEN_RE = re.compile(r"[0-9a-z\u4e00-\u9fff]+")


class TaskWorkspacePlanner:
    """Compile workspace plans into task graphs and metadata."""

    def __init__(self, runtime_state):
        self._runtime_state = runtime_state
        self._cards = TaskCardTemplateFactory()

    def compile_workspace_plan(
        self,
        workspace: TaskWorkspace,
        *,
        brain,
        orchestration_service,
        plugin_service,
        research_runtime_service,
        permission_resolver,
    ) -> TaskWorkspace:
        builder_state = self._builder_state(workspace)
        builder_draft = self._builder_draft(builder_state)
        compiled_mode = self._compiled_mode(workspace, builder_draft)
        context = BrainTaskContext(
            thread_id=workspace.task_id,
            user_goal=workspace.goal or workspace.summary or workspace.name,
            constraints=self._brain_constraints(workspace, builder_draft),
            evidence=workspace.metadata.get("evidence", []),
            preferred_mode=self._preferred_mode(builder_draft),
            memory_hints=[
                item
                for item in [
                    str(workspace.metadata.get("project_memory_digest") or "").strip(),
                    str(workspace.metadata.get("last_agent_result_summary") or "").strip(),
                    (
                        "checkpoint_labels="
                        + ", ".join(checkpoint.label for checkpoint in workspace.checkpoints[:3])
                        if workspace.checkpoints
                        else ""
                    ),
                ]
                if item
            ],
        )
        brain_response = brain.run(context)
        compiled_graph = orchestration_service.compile_brain_response(
            brain_response,
            task_id=workspace.task_id,
            mode=compiled_mode,
        )
        research_experiment_id = self._resolve_research_experiment_id(
            workspace,
            compiled_graph,
            research_runtime_service,
        )
        workspace.card_graph = self._compiled_graph_to_task_graph(
            workspace,
            compiled_graph,
            builder_draft=builder_draft,
            compiled_mode=compiled_mode,
            builder_revision=int(builder_state.get("revision") or 0),
            research_experiment_id=research_experiment_id,
            permission_resolver=permission_resolver,
        )
        plugin_recommendation = plugin_service.recommend_plugins(
            mode=workspace.mode,
            card_kinds=[card.kind for card in workspace.card_graph.cards],
        )
        workspace.status = "planned"
        workspace.updated_at = utc_now()
        workspace.metadata.update(
            {
                "brain_plan_summary": brain_response.plan.summary,
                "brain_decision": brain_response.decision.recommendation,
                "compiled_graph_id": compiled_graph.graph_id,
                "langgraph_graph_id": compiled_graph.graph_id,
                "langgraph_assistant_id": str(workspace.metadata.get("langgraph_assistant_id") or "lead_agent"),
                "compiled_mode": compiled_mode,
                "builder_compiled_revision": int(builder_state.get("revision") or 0),
                "builder_compiled_action_ids": self._applied_action_ids(builder_state),
                "compiled_failure_policy": builder_draft.get("failurePolicy") if isinstance(builder_draft.get("failurePolicy"), dict) else {},
                "compiled_route": builder_draft.get("route") if isinstance(builder_draft.get("route"), list) else [],
                "compiled_collaboration_style": str(builder_draft.get("collaborationStyle") or "").strip(),
                "compiled_handoff_count": len(compiled_graph.handoffs),
                "compiled_ready_card_count": sum(
                    1
                    for card in compiled_graph.cards
                    if card.runtime_binding is not None and card.runtime_binding.state == "ready"
                ),
                "compiled_blocked_card_count": sum(
                    1
                    for card in compiled_graph.cards
                    if card.runtime_binding is not None and card.runtime_binding.state == "blocked"
                ),
                "compiled_review_card_count": sum(1 for card in compiled_graph.cards if card.kind == "review"),
                "compiled_checkpoint_card_count": sum(
                    1 for card in compiled_graph.cards if card.kind == "checkpoint"
                ),
                "compiled_requires_final_review": any(
                    handoff.destination == "review_queue" for handoff in compiled_graph.handoffs
                ),
                "research_experiment_id": research_experiment_id,
                "plan_items": [step.title for step in brain_response.plan.steps],
                "recommended_plugin_ids": plugin_recommendation.plugin_ids,
                "active_plugin_ids": plugin_recommendation.plugin_ids,
            }
        )
        self._runtime_state.refresh_memory_digest(workspace)
        for agent in workspace.agents:
            if agent.linked_card_id is not None:
                agent.status = "queued"
        workspace.progress = self._runtime_state.progress(workspace)
        return workspace

    def _builder_state(self, workspace: TaskWorkspace) -> dict:
        state = workspace.metadata.get("brain_builder_state")
        return dict(state) if isinstance(state, dict) else {}

    def _builder_draft(self, builder_state: dict) -> dict:
        draft = builder_state.get("current_draft")
        return dict(draft) if isinstance(draft, dict) else {}

    def _applied_action_ids(self, builder_state: dict) -> list[str]:
        action_ids = builder_state.get("applied_action_ids")
        if not isinstance(action_ids, list):
            return []
        return [item for item in action_ids if isinstance(item, str) and item.strip()]

    def _preferred_mode(self, builder_draft: dict) -> str:
        brain_config = builder_draft.get("brainConfig")
        if isinstance(brain_config, dict):
            preferred_mode = brain_config.get("preferredMode")
            if preferred_mode in {"plan", "research", "quant", "policy"}:
                return preferred_mode
        return "plan"

    def _compiled_mode(self, workspace: TaskWorkspace, builder_draft: dict) -> str:
        requested_mode = builder_draft.get("mode")
        if requested_mode == "branch":
            return "branch"
        if requested_mode == "group":
            return "group"
        if requested_mode == "task":
            return "single"
        return workspace.mode

    def _brain_constraints(self, workspace: TaskWorkspace, builder_draft: dict) -> list[str]:
        constraints = [
            item
            for item in workspace.metadata.get("constraints", [])
            if isinstance(item, str) and item.strip()
        ]
        failure_policy = builder_draft.get("failurePolicy")
        if isinstance(failure_policy, dict):
            on_final_failure = failure_policy.get("onFinalFailure")
            max_total_steps = failure_policy.get("maxTotalSteps")
            max_step_attempts = failure_policy.get("maxStepAttempts")
            max_no_progress_rounds = failure_policy.get("maxNoProgressRounds")
            if isinstance(on_final_failure, str) and on_final_failure.strip():
                constraints.append(f"on_final_failure:{on_final_failure}")
            if isinstance(max_total_steps, int):
                constraints.append(f"max_total_steps:{max_total_steps}")
            if isinstance(max_step_attempts, int):
                constraints.append(f"max_step_attempts:{max_step_attempts}")
            if isinstance(max_no_progress_rounds, int):
                constraints.append(f"max_no_progress_rounds:{max_no_progress_rounds}")
        route = builder_draft.get("route")
        if isinstance(route, list) and route:
            constraints.append(f"route_length:{len(route)}")
        collaboration_style = builder_draft.get("collaborationStyle")
        if isinstance(collaboration_style, str) and collaboration_style.strip():
            constraints.append(f"collaboration_style:{collaboration_style}")
        return constraints

    def _resolve_research_experiment_id(
        self,
        workspace: TaskWorkspace,
        compiled_graph: CompiledTaskGraph,
        research_runtime_service,
    ) -> str | None:
        if not any(card.kind == "research" for card in compiled_graph.cards):
            return None
        experiment = research_runtime_service.ensure_workspace_experiment(
            task_id=workspace.task_id,
            goal=workspace.goal or workspace.summary or workspace.name,
            candidate_files=workspace.metadata.get("candidate_files", []),
        )
        return experiment.experiment_id

    def _compiled_graph_to_task_graph(
        self,
        workspace: TaskWorkspace,
        compiled_graph: CompiledTaskGraph,
        *,
        builder_draft: dict,
        compiled_mode: str,
        builder_revision: int,
        research_experiment_id: str | None,
        permission_resolver,
    ) -> TaskCardGraph:
        existing_cards = list(workspace.card_graph.cards)
        existing_project = next(
            (
                card
                for card in existing_cards
                if card.kind == "start" or "project" in card.tags or "entry" in card.tags
            ),
            None,
        )
        existing_by_agent = {
            card.linked_agent_id: card
            for card in existing_cards
            if card.linked_agent_id is not None
        }

        cards: list[TaskCard] = []
        edges: list[TaskCardEdge] = []
        project_card_id = existing_project.card_id if existing_project is not None else make_id("card")
        project_position = self._carry_position(existing_project)
        cards.append(
            self._cards.create(
                card_id=project_card_id,
                kind="start",
                title=workspace.name or "Project Info",
                description=workspace.goal or workspace.summary or "Workflow project entry point.",
                config={
                    "goal": workspace.goal,
                    "summary": workspace.summary,
                    "mode": compiled_mode,
                    "topology": compiled_mode,
                    "compiled_graph_id": compiled_graph.graph_id,
                    "compiled_plan_summary": compiled_graph.source_plan_summary,
                    "builder_revision": builder_revision,
                    "builder_draft": builder_draft,
                    "compiled_budget_policy": compiled_graph.budget_policy.model_dump(mode="json"),
                    "document_path": CANONICAL_PROJECT_DOC,
                    "document_role": "project",
                    "result_document_path": CANONICAL_RESULT_DOC,
                    **({"position": project_position} if project_position is not None else {}),
                },
                tags=["project", "entry"],
                ui={"variant": "entry", "accent": "task"},
            )
        )

        agent_card_ids: list[str] = []
        for index, agent in enumerate(workspace.agents):
            existing_card = existing_by_agent.get(agent.agent_id)
            card_id = (
                existing_card.card_id
                if existing_card is not None
                else agent.linked_card_id or make_id("card")
            )
            agent.linked_card_id = card_id
            agent_card_ids.append(card_id)
            cards.append(
                self._cards.create(
                    card_id=card_id,
                    kind="agent",
                    title=agent.name,
                    description=agent.task_scope or agent.role,
                    linked_agent_id=agent.agent_id,
                    permission_mode=permission_resolver(workspace, agent),
                    config={
                        "role": agent.role,
                        "model_name": agent.model_name,
                        "agent_name": agent.name,
                        "agent_role": agent.role,
                        "branch_task": agent.task_scope,
                        "prompt_preview": self._prompt_preview(workspace, agent, is_primary=index == 0),
                        "compiled_mode": compiled_mode,
                        "builder_route": builder_draft.get("route") if isinstance(builder_draft.get("route"), list) else [],
                        "failure_policy": builder_draft.get("failurePolicy") if isinstance(builder_draft.get("failurePolicy"), dict) else {},
                        "document_path": CANONICAL_SETTINGS_DOC,
                        "document_role": "workflow_settings",
                        "research_experiment_id": research_experiment_id,
                        **({"position": self._carry_position(existing_card)} if self._carry_position(existing_card) is not None else {}),
                    },
                    tags=["agent", "primary" if index == 0 else "sub-agent"],
                    ui={"variant": "agent", "role": agent.role, "is_primary": index == 0},
                )
            )

        if agent_card_ids:
            edges.append(
                TaskCardEdge(
                    edge_id=make_id("edge"),
                    source_card_id=project_card_id,
                    target_card_id=agent_card_ids[0],
                    label="orchestrates",
                )
            )

        if compiled_mode == "branch":
            for card_id in agent_card_ids[1:]:
                edges.append(
                    TaskCardEdge(
                        edge_id=make_id("edge"),
                        source_card_id=agent_card_ids[0],
                        target_card_id=card_id,
                        label="dispatches",
                    )
                )
        elif compiled_mode == "group":
            if len(agent_card_ids) > 1:
                for index, card_id in enumerate(agent_card_ids):
                    target_id = agent_card_ids[(index + 1) % len(agent_card_ids)]
                    edges.append(
                        TaskCardEdge(
                            edge_id=make_id("edge"),
                            source_card_id=card_id,
                            target_card_id=target_id,
                            label="collaborates",
                        )
                    )
        else:
            for source_id, target_id in zip(agent_card_ids, agent_card_ids[1:], strict=False):
                edges.append(
                    TaskCardEdge(
                        edge_id=make_id("edge"),
                        source_card_id=source_id,
                        target_card_id=target_id,
                        label="chain",
                    )
                )

        return TaskCardGraph(cards=cards, edges=edges)

    @staticmethod
    def _carry_position(card: TaskCard | None) -> dict[str, float] | None:
        if card is None:
            return None
        position = card.config.get("position") if isinstance(card.config, dict) else None
        if not isinstance(position, dict):
            return None
        try:
            x = float(position.get("x"))
            y = float(position.get("y"))
        except (TypeError, ValueError):
            return None
        return {"x": x, "y": y}

    def _prompt_preview(self, workspace: TaskWorkspace, agent, *, is_primary: bool) -> str:
        if is_primary:
            if workspace.mode == "branch":
                return (
                    f"你是主协调 agent。任务目标：{workspace.goal or workspace.name}。\n"
                    "先拆分分支任务，再监督各子 agent 返回可验证结果，最后汇总。"
                )
            if workspace.mode == "group":
                return (
                    f"你是群聊主 agent。任务目标：{workspace.goal or workspace.name}。\n"
                    "负责维持群组协作节奏，并基于各成员真实产出做最终收口。"
                )
            return (
                f"你是主执行 agent。任务目标：{workspace.goal or workspace.name}。\n"
                "直接完成任务，输出可验证结果与必要证据。"
            )
        return (
            f"你是 {agent.name}，职责：{agent.task_scope or agent.role}。\n"
            f"围绕总任务“{workspace.goal or workspace.name}”只完成你负责的分支工作，返回可验证结果。"
        )

    def _resolve_linked_agent(self, workspace: TaskWorkspace, card) -> tuple[object | None, int]:
        if not workspace.agents:
            return None, 0

        best_agent = None
        best_score = -1
        card_tokens = self._card_tokens(card.title, card.kind)
        for index, agent in enumerate(workspace.agents):
            score = self._agent_binding_score(agent, card.kind, card_tokens, index)
            if score > best_score:
                best_agent = agent
                best_score = score

        if best_agent is not None and best_score > 0:
            return best_agent, best_score

        if card.kind == "review":
            fallback = select_reviewer_agent(list(workspace.agents))
            return fallback, 100 if fallback is not None else 0
        if card.kind == "research":
            fallback = next(
                (
                    agent
                    for agent in workspace.agents
                    if any(token in {"research", "researcher"} for token in self._agent_tokens(agent))
                ),
                None,
            )
            return fallback, 80 if fallback is not None else 0
        fallback = select_lead_agent(list(workspace.agents))
        return fallback, 10

    def _agent_binding_score(self, agent, card_kind: str, card_tokens: set[str], index: int) -> int:
        agent_tokens = self._agent_tokens(agent)
        score = 0

        if card_kind == "review" and is_reviewer_role(agent.role):
            score += 200
        if card_kind == "research" and any(token in {"research", "researcher"} for token in agent_tokens):
            score += 160
        if card_kind == "agent" and is_management_role(agent.role):
            score += 80
        if card_kind == "agent" and any(token in {"builder", "coder", "implementation", "implement"} for token in card_tokens):
            if any(token in {"builder", "coder", "implementation", "implement"} for token in agent_tokens):
                score += 120

        overlap = card_tokens.intersection(agent_tokens)
        score += len(overlap) * 24

        if index == 0 and card_kind == "agent":
            score += 8
        return score

    @staticmethod
    def _agent_tokens(agent) -> set[str]:
        tokens: set[str] = set()
        for value in (agent.role, agent.name, agent.task_scope or ""):
            tokens.update(_TOKEN_RE.findall(value.lower()))
        return tokens

    @staticmethod
    def _card_tokens(title: str, kind: str) -> set[str]:
        tokens = set(_TOKEN_RE.findall(f"{title} {kind}".lower()))
        if kind == "review":
            tokens.update({"review", "reviewer"})
        if kind == "research":
            tokens.update({"research", "researcher"})
        return tokens
