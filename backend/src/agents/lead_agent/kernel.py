from __future__ import annotations

from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig

from .builder import LeadAgentBuilder
from .runtime import LeadAgentRuntimeOptions, LeadAgentRuntimeResolver

_DEFAULT_OCTO_LIFECYCLE_STATES = (
    "builder_applying",
    "checkpoint_ready",
    "hook_executing",
    "human_review_required",
    "signal_wait",
)


def _resolve_lifecycle_states() -> tuple[str, ...]:
    try:
        from src.storage.workflow.status import LIFECYCLE_STATES

        return tuple(sorted(LIFECYCLE_STATES))
    except Exception:
        return _DEFAULT_OCTO_LIFECYCLE_STATES


@dataclass(frozen=True, slots=True)
class LeadAgentKernelContract:
    name: str
    execution_mode: str
    lifecycle_model: str
    runtime_contract_version: str
    memory_contract: str
    capability_contract: str
    lifecycle_states: tuple[str, ...]


class OctoLeadAgentKernel:
    """Compatibility facade that expresses the default single-agent path as an Octo-native kernel."""

    def __init__(
        self,
        *,
        runtime_resolver: LeadAgentRuntimeResolver,
        builder: LeadAgentBuilder,
    ) -> None:
        self._runtime_resolver = runtime_resolver
        self._builder = builder

    def contract(self) -> LeadAgentKernelContract:
        return LeadAgentKernelContract(
            name="octo_native",
            execution_mode="single_default",
            lifecycle_model="octo_native",
            runtime_contract_version="v1",
            memory_contract="layered_v1",
            capability_contract="registry_v1",
            lifecycle_states=_resolve_lifecycle_states(),
        )

    def resolve(self, config: RunnableConfig) -> LeadAgentRuntimeOptions:
        return self._runtime_resolver.resolve(config)

    def build(self, config: RunnableConfig):
        options = self.resolve(config)
        LeadAgentRuntimeResolver.inject_metadata(config, options)
        self.inject_kernel_metadata(config, options)
        return self._builder.build(config, options)

    def inject_kernel_metadata(
        self,
        config: RunnableConfig,
        options: LeadAgentRuntimeOptions,
    ) -> None:
        metadata = config.setdefault("metadata", {})
        contract = self.contract()
        metadata.update(
            {
                "lead_agent_kernel": contract.name,
                "lead_agent_execution_mode": contract.execution_mode,
                "lead_agent_lifecycle_model": contract.lifecycle_model,
                "lead_agent_runtime_contract": contract.runtime_contract_version,
                "lead_agent_memory_contract": contract.memory_contract,
                "lead_agent_capability_contract": contract.capability_contract,
                "lead_agent_lifecycle_states": list(contract.lifecycle_states),
                "lead_agent_model_name": options.model_name,
            }
        )
