"""Project service — lightweight wrapper around task workspaces with memory isolation."""

from __future__ import annotations

from .memory import ProjectMemoryService, get_project_memory_service
from .service import ProjectService, get_project_service

__all__ = [
    "ProjectMemoryService",
    "ProjectService",
    "get_project_memory_service",
    "get_project_service",
]
