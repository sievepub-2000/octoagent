"""Built-in subagent configurations."""

from .bash_agent import BASH_AGENT_CONFIG
from .coder_agent import CODER_AGENT_CONFIG
from .general_purpose import GENERAL_PURPOSE_CONFIG
from .operator_agent import OPERATOR_AGENT_CONFIG
from .planner_agent import PLANNER_AGENT_CONFIG
from .reviewer_agent import REVIEWER_AGENT_CONFIG
from .teacher_agent import TEACHER_AGENT_CONFIG
from .local_model_agent import LOCAL_MODEL_AGENT_CONFIG

__all__ = [
    "GENERAL_PURPOSE_CONFIG",
    "BASH_AGENT_CONFIG",
    "PLANNER_AGENT_CONFIG",
    "CODER_AGENT_CONFIG",
    "OPERATOR_AGENT_CONFIG",
    "REVIEWER_AGENT_CONFIG",
    "TEACHER_AGENT_CONFIG",
]

# Registry of built-in subagents
BUILTIN_SUBAGENTS = {
    "general-purpose": GENERAL_PURPOSE_CONFIG,
    "bash": BASH_AGENT_CONFIG,
    "planner": PLANNER_AGENT_CONFIG,
    "coder": CODER_AGENT_CONFIG,
    "operator": OPERATOR_AGENT_CONFIG,
    "reviewer": REVIEWER_AGENT_CONFIG,
    "teacher": TEACHER_AGENT_CONFIG,
    "local-model": LOCAL_MODEL_AGENT_CONFIG,
}
