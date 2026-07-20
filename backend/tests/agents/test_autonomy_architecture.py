from __future__ import annotations

from src.agents.core.instruction_contracts import detect_instruction_contract
from src.agents.lead_agent import agent as agent_module
from src.runtime.config.model_config import ModelConfig
from src.runtime.config.system_guard_config import SystemGuardConfig


class _AppConfig:
    def __init__(self) -> None:
        self.models = [
            ModelConfig(
                name="local-agent",
                model="local-agent",
                provider_name="llamacpp",
                interface_type="openai_compatible",
                supports_thinking=True,
                max_context_tokens=131_072,
            )
        ]

    def get_model_config(self, name: str) -> ModelConfig | None:
        return next((model for model in self.models if model.name == name), None)


def test_lead_chain_keeps_execution_seams_without_reasoning_rewriters() -> None:
    original_getter = agent_module.get_app_config
    agent_module.get_app_config = lambda: _AppConfig()
    try:
        middlewares = agent_module._build_middlewares(
            {"configurable": {"mode": "pro", "permission_mode": "directory"}},
            "local-agent",
        )
    finally:
        agent_module.get_app_config = original_getter

    names = {middleware.__class__.__name__ for middleware in middlewares}
    assert {
        "StateMiddleware",
        "ContinuationMiddleware",
        "SandboxMiddleware",
        "RuntimeStateMiddleware",
        "DangerousToolConfirmationMiddleware",
        "ToolExecutionGuardMiddleware",
        "SessionCompactionMiddleware",
    } <= names
    assert names.isdisjoint(
        {
            "InstructionContractMiddleware",
            "GoalMiddleware",
            "ExecutionMiddleware",
            "ProgressStallMiddleware",
            "StepReflectionMiddleware",
            "SkillEvolutionMiddleware",
            "ClientCommandMiddleware",
            "HookDispatchMiddleware",
        }
    )


def test_resume_language_is_not_reclassified_as_web_research() -> None:
    contract = detect_instruction_contract(
        "Continue the unfinished work using the recent context and current task state."
    )

    assert contract.intent == "general"
    assert contract.required_tool_categories == ()


def test_code_task_with_recent_context_stays_a_code_task() -> None:
    contract = detect_instruction_contract(
        "Review the recent context, inspect the repository, and fix the failing code."
    )

    assert contract.intent == "code_task"
    assert contract.required_tool_categories == ("filesystem", "tests")


def test_startup_guard_does_not_ask_the_agent_to_repair_itself_by_default() -> None:
    assert SystemGuardConfig().invoke_default_agent_on_issue is False
