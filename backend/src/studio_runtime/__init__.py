"""Studio Runtime — Rowboat-style visual workflow execution engine.

Provides compiled workflow execution, pause/resume lifecycle, and
bridge to task_workspaces for actual agent dispatch.
"""

from .service import StudioRuntimeService, get_studio_runtime_service

__all__ = ["StudioRuntimeService", "get_studio_runtime_service"]
