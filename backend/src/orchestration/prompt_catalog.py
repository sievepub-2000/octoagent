"""Prompt stack catalog for orchestration-owned execution profiles."""

from __future__ import annotations

from .contracts import PromptModuleProfile, PromptStackProfile


class OrchestrationPromptCatalog:
    """Own repository prompt stack definitions."""

    def list_prompt_stacks(self) -> list[PromptStackProfile]:
        return [
            PromptStackProfile(
                profile_id="octopus-coding-agent-stack",
                title="Octopus Coding Agent Prompt Stack",
                modules=[
                    PromptModuleProfile(
                        module_id="identity",
                        stage="identity",
                        title="Identity",
                        purpose="Define platform role, execution boundaries, and collaboration style.",
                        dynamic_inputs=["product_mode", "operator_mode"],
                        instruction_template=(
                            "You are OctoAgent, a repository-owned software engineering agent. "
                            "Work inside the current repository and active task session, stay factual and direct, "
                            "and optimize for finishing the user's requested work with reviewable changes."
                        ),
                    ),
                    PromptModuleProfile(
                        module_id="workflow",
                        stage="workflow",
                        title="Workflow",
                        purpose="Drive plan, act, verify, and summarize loops for coding tasks.",
                        dynamic_inputs=["task_goal", "acceptance_criteria"],
                        instruction_template=(
                            "Understand the goal, inspect the relevant code and docs, choose the smallest valid execution path, "
                            "implement only what is needed, verify with tests or direct checks, and report concrete outcomes."
                        ),
                    ),
                    PromptModuleProfile(
                        module_id="context_snapshot",
                        stage="context",
                        title="Context Snapshot",
                        purpose="Inject repo instructions, git status, file tree, and active docs.",
                        dynamic_inputs=["git_status", "repo_tree", "workspace_docs"],
                        instruction_template=(
                            "Treat the repository context snapshot as the working baseline. Respect the current task mode, "
                            "compiled graph, active docs, and runtime selections before acting."
                        ),
                    ),
                    PromptModuleProfile(
                        module_id="reminder_start",
                        stage="reminder",
                        title="Reminder Start",
                        purpose="Load task-local runtime constraints before tool execution.",
                        dynamic_inputs=["approval_mode", "budget_policy"],
                        instruction_template=(
                            "Before each action, check whether the step needs approval, whether a safer inspection path exists, "
                            "and whether the current budget and runtime ownership allow the action."
                        ),
                    ),
                    PromptModuleProfile(
                        module_id="reminder_end",
                        stage="reminder",
                        title="Reminder End",
                        purpose="Reload short-term task state, todos, and pending handoffs.",
                        dynamic_inputs=["todo_state", "handoff_state"],
                        instruction_template=(
                            "After each meaningful action, preserve unresolved items, restate the current state, and keep the next "
                            "step aligned with the active handoff, checkpoints, and execution flow."
                        ),
                    ),
                    PromptModuleProfile(
                        module_id="topic_router",
                        stage="routing",
                        title="Topic Router",
                        purpose="Detect whether the next turn should resume, compact, branch, or start a new task.",
                        dynamic_inputs=["conversation_summary", "current_goal"],
                        instruction_template=(
                            "Route the next turn intentionally: continue if the goal is unchanged, compact when context is stale, "
                            "handoff when another runtime owns the next step, and avoid unrelated work."
                        ),
                    ),
                    PromptModuleProfile(
                        module_id="compact",
                        stage="compaction",
                        title="Compaction",
                        purpose="Compress exhausted context into a reusable summary with active constraints and open items.",
                        dynamic_inputs=["conversation_history", "artifact_refs"],
                        instruction_template=(
                            "When context grows, summarize durable decisions, active constraints, open questions, and artifact refs. "
                            "Drop repetition and leave the next session executable."
                        ),
                    ),
                    PromptModuleProfile(
                        module_id="summarize_previous",
                        stage="summarization",
                        title="Summarize Previous",
                        purpose="Load previous session summaries into the next session without replaying full context.",
                        dynamic_inputs=["thread_history", "previous_summary"],
                        instruction_template=(
                            "Use previous-session summaries as compressed working memory. Reuse them to resume quickly, "
                            "but re-check any fact that depends on current repository state."
                        ),
                    ),
                    PromptModuleProfile(
                        module_id="permission_policy",
                        stage="policy",
                        title="Permission Policy",
                        purpose="Explain when to auto-allow safe reads and when to require explicit approval.",
                        dynamic_inputs=["tool_policy", "risk_labels"],
                        instruction_template=(
                            "Auto-allow safe inspection work, require approval for writes and side effects, and block actions "
                            "that violate explicit policy or move outside the active repository and runtime boundaries."
                        ),
                    ),
                    PromptModuleProfile(
                        module_id="working_memory",
                        stage="reminder",
                        title="Working Memory",
                        purpose="Carry forward the active plan and durable short-term memory without replaying raw history.",
                        dynamic_inputs=["plan_items", "checkpoints", "session_summaries"],
                        instruction_template=(
                            "Keep the current plan, unresolved blockers, checkpoints, and durable repository decisions visible. "
                            "Prefer compact working memory over replaying stale transcript content."
                        ),
                    ),
                    PromptModuleProfile(
                        module_id="self_review",
                        stage="policy",
                        title="Self Review",
                        purpose="Require a bounded self-check before claiming completion or handing off work.",
                        dynamic_inputs=["review_required", "self_review_checklist"],
                        instruction_template=(
                            "Before claiming completion, review the requested behavior, changed or inspected surfaces, verification "
                            "results, and obvious regressions. Escalate to review paths when the task warrants it."
                        ),
                    ),
                    PromptModuleProfile(
                        module_id="coordinator_mode",
                        stage="routing",
                        title="Coordinator Mode",
                        purpose="Coordinate multi-agent work without losing plan ownership or sequencing.",
                        dynamic_inputs=["session_mode", "coordination_strategy", "agent_roles"],
                        instruction_template=(
                            "If the session is in coordinator mode, decompose the work into bounded worker tasks, keep the central "
                            "plan current, synthesize worker results, and avoid delegating urgent blocking decisions."
                        ),
                    ),
                    PromptModuleProfile(
                        module_id="model_routing",
                        stage="policy",
                        title="Model Routing",
                        purpose="Select an adequate model path for reasoning depth, context size, and modality needs.",
                        dynamic_inputs=["model_profile", "context_pressure", "requires_vision"],
                        instruction_template=(
                            "Choose the smallest adequate model path for the current turn's reasoning, context, and modality needs. "
                            "Prefer stable fallbacks over brittle premium-only assumptions."
                        ),
                    ),
                ],
                source_alignment=[
                    "Claude-Code-Leak context and tool loop architecture",
                    "claude-code-reverse prompt-stack decomposition",
                    "claude-code-sourcemap restored package structure",
                    "claude-code-source-code query engine and system prompt section model",
                ],
                notes=[
                    "Repository-owned prompt modules must be rewritten, not copied from third-party prompts.",
                    "Prompt stack is model-agnostic and routed through OctoAgent contracts.",
                    "A dedicated QueryEngine layer should own the turn loop between task sessions and provider calls.",
                    "Coordinator, review, memory, permission, and model-routing semantics stay inside one prompt stack.",
                ],
            )
        ]
