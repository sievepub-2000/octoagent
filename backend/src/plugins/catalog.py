"""Built-in plugin manifest catalog."""

from __future__ import annotations

from .contracts import PluginCommand, PluginManifest


class PluginCatalog:
    """Own built-in plugin manifests."""

    def seed_manifests(self) -> list[PluginManifest]:
        return [
            PluginManifest(
                plugin_id="compound-engineering-review",
                display_name="Compound Engineering Review",
                version="0.1.0",
                description=(
                    "Review-oriented engineering workflow plugin with explicit plan, work, "
                    "review, and compound capture stages."
                ),
                commands=[
                    PluginCommand(
                        command_id="ce:brainstorm",
                        title="Brainstorm",
                        stage="brainstorm",
                        summary="Refine problem framing before technical planning.",
                    ),
                    PluginCommand(
                        command_id="ce:plan",
                        title="Plan",
                        stage="plan",
                        summary="Produce an implementation plan with risks, interfaces, and sequencing.",
                    ),
                    PluginCommand(
                        command_id="ce:review",
                        title="Review",
                        stage="review",
                        summary="Run pre-merge review with artifact and policy awareness.",
                    ),
                ],
                installation_targets=["codex", "claude", "opencode"],
                review_flow=["brainstorm", "plan", "work", "review", "compound"],
            ),
            PluginManifest(
                plugin_id="workspace-runtime-bridge",
                display_name="Workspace Runtime Bridge",
                version="0.1.0",
                description="Bind task-workspace cards to runtime-facing command surfaces and approvals.",
                commands=[
                    PluginCommand(
                        command_id="wrb:bind",
                        title="Bind Runtime",
                        stage="runtime",
                        summary="Attach runtime bindings and policy labels to task cards.",
                    ),
                    PluginCommand(
                        command_id="wrb:review",
                        title="Review Runtime",
                        stage="review",
                        summary="Review runtime side effects and approval checkpoints before execution.",
                    ),
                ],
                installation_targets=["octoagent", "codex"],
                review_flow=["plan", "runtime", "review"],
            ),
        ]
