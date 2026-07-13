"""Persistent project definitions and execution policy."""

from __future__ import annotations

from .service import ProjectExecutionContext, ProjectService, get_project_service

__all__ = ["ProjectExecutionContext", "ProjectService", "get_project_service"]
