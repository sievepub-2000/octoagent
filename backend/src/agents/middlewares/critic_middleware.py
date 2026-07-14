"""CriticMiddleware - Placeholder implementation.

This middleware was migrated to harness hooks but the file was accidentally deleted.
Keeping a minimal stub to avoid import errors.
"""

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class CriticMiddleware(AgentMiddleware):
    """Minimal critic middleware stub."""

    def __init__(self) -> None:
        super().__init__()

    def after_model(self, state: Any, runtime: Runtime) -> Any:
        """Process after model response (stub).

        Args:
            state: The current agent state.
            runtime: The runtime environment.

        Returns:
            Modified state or None.
        """
        try:
            # Placeholder for critic logic - migrated to harness hooks
            return state
        except Exception as e:  # noqa: BLE001
            logger.warning("CriticMiddleware.after_model failed: %s", e)
            return None  # Never block the main response
