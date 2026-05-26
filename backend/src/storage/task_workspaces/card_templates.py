"""Unified task card template factory."""

from __future__ import annotations

from typing import Any

from src.runtime.config.ml_intern_defaults import build_ml_intern_runtime_context

from .contracts import TaskAgentPermissionMode, TaskCard, TaskCardKind, TaskCardStatus


class TaskCardTemplateFactory:
    """Create task cards through a single configurable template surface."""

    def create(
        self,
        *,
        card_id: str,
        kind: TaskCardKind,
        title: str,
        description: str | None = None,
        status: TaskCardStatus = "configured",
        linked_agent_id: str | None = None,
        permission_mode: TaskAgentPermissionMode = "workspace",
        config: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        ui: dict[str, Any] | None = None,
    ) -> TaskCard:
        merged_config = dict(config or {})
        ml_intern_context = build_ml_intern_runtime_context(permission_mode=permission_mode)
        merged_config.setdefault("ml_intern_profile", ml_intern_context["ml_intern_profile"])
        merged_config.setdefault("ml_intern_defaults", ml_intern_context["ml_intern_defaults"])
        ui_config = dict(ui or {})
        if ui_config:
            merged_config["ui"] = ui_config
        return TaskCard(
            card_id=card_id,
            kind=kind,
            title=title,
            description=description,
            status=status,
            linked_agent_id=linked_agent_id,
            permission_mode=permission_mode,
            config=merged_config,
            tags=list(tags or []),
        )
