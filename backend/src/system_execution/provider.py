"""Provider abstraction for system-level execution backends."""

from __future__ import annotations

from typing import Protocol

from .contracts import (
    SystemExecutionCapability,
    SystemExecutionPlan,
    SystemExecutionPlanRequest,
    SystemExecutionSession,
)


class SystemExecutionProvider(Protocol):
    name: str

    def get_capability(self) -> SystemExecutionCapability: ...

    def plan(self, request: SystemExecutionPlanRequest) -> SystemExecutionPlan: ...

    def create_session(
        self,
        request: SystemExecutionPlanRequest,
        *,
        dry_run: bool = True,
    ) -> SystemExecutionSession: ...
