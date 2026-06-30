"""CriticMiddleware - Placeholder implementation.

This middleware was migrated to harness hooks but the file was accidentally deleted.
Keeping a minimal stub to avoid import errors.
"""

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime


class CriticMiddleware(AgentMiddleware):
    """Minimal critic middleware stub."""

    def __init__(self) -> None:
        super().__init__()

    def after_model(self, state, runtime: Runtime):
        return None
