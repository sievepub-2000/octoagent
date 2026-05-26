from .config import SubagentConfig
from .contracts import SubagentResult, SubagentStatus
from .registry import get_subagent_config, get_subagent_names, list_subagents


def __getattr__(name: str):
    if name == "SubagentExecutor":
        from .executor import SubagentExecutor

        return SubagentExecutor
    if name == "get_subagent_service":
        from .service import get_subagent_service

        return get_subagent_service
    raise AttributeError(name)


__all__ = [
    "SubagentConfig",
    "SubagentExecutor",
    "SubagentResult",
    "SubagentStatus",
    "get_subagent_config",
    "get_subagent_names",
    "get_subagent_service",
    "list_subagents",
]
