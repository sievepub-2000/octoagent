from __future__ import annotations

from src.agents.core.instruction_contracts import detect_instruction_contract
from src.agents.lead_agent import agent as agent_module
from src.agents.lead_agent.builder import resolve_tool_binding_scope
from src.runtime.config.model_config import ModelConfig


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


def test_tool_discovery_uses_core_narrow_waist_only() -> None:
    scope = resolve_tool_binding_scope(
        "请调用 list_capabilities 查看当前真实工具",
        dialogue_route="tool_action",
        configured_groups=None,
    )

    assert scope.groups == []
    assert scope.include_mcp is False


def test_code_task_loads_only_file_and_shell_groups() -> None:
    scope = resolve_tool_binding_scope(
        "检查仓库代码并修复测试，然后提交 git",
        dialogue_route="deep_agent",
        configured_groups=None,
    )

    assert scope.groups == ["file:read", "file:write", "bash"]
    assert scope.include_mcp is False


def test_explicit_mcp_task_enables_mcp_without_loading_all_configured_groups() -> None:
    scope = resolve_tool_binding_scope(
        "通过 MCP 查询已连接的 PostgreSQL 服务",
        dialogue_route="tool_action",
        configured_groups=None,
    )

    assert scope.groups == []
    assert scope.include_mcp is True
