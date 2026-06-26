"""Project service — lightweight wrapper around task workspaces with memory isolation."""

from __future__ import annotations

from .service import ProjectService, get_project_service
from .memory import ProjectMemoryService, get_project_memory_service

__all__ = [
    "ProjectService",
    "get_project_service",
    "ProjectMemoryService",
    "get_project_memory_service",
]
