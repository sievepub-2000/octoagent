"""Service facade for the orchestration plane."""

from __future__ import annotations

from .compiler import OrchestrationCompiler
from .contracts import CompiledTaskGraph, OrchestrationCapability, PromptStackProfile
from .prompt_catalog import OrchestrationPromptCatalog


class OrchestrationService:
    """Facade over orchestration capability, prompt stacks, and graph compilation."""

    def __init__(self):
        self._prompts = OrchestrationPromptCatalog()
        self._compiler = OrchestrationCompiler()

    def get_capability(self) -> OrchestrationCapability:
        return OrchestrationCapability()

    def list_prompt_stacks(self) -> list[PromptStackProfile]:
        return self._prompts.list_prompt_stacks()

    def get_seed_graph(self) -> CompiledTaskGraph:
        return self._compiler.get_seed_graph()

    def compile_brain_response(
        self,
        response,
        *,
        task_id: str,
        mode,
    ) -> CompiledTaskGraph:
        return self._compiler.compile_brain_response(response, task_id=task_id, mode=mode)


_service = OrchestrationService()


def get_orchestration_service() -> OrchestrationService:
    return _service
