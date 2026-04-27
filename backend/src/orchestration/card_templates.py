"""Unified template helpers for orchestration cards."""

from __future__ import annotations

from typing import Any

from .contracts import OrchestrationCard, RuntimeBinding


class OrchestrationCardTemplateFactory:
    """Create orchestration cards through one template surface."""

    def create(
        self,
        *,
        card_id: str,
        title: str,
        kind: str,
        dependencies: list[str] | None = None,
        runtime_binding: RuntimeBinding | None = None,
        template_id: str | None = None,
        ui: dict[str, Any] | None = None,
    ) -> OrchestrationCard:
        return OrchestrationCard(
            card_id=card_id,
            title=title,
            kind=kind,
            dependencies=list(dependencies or []),
            runtime_binding=runtime_binding,
            template_id=template_id or f"orchestration.{kind}",
            ui=dict(ui or {}),
        )
