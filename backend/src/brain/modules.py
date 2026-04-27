"""Composable analysis-module registry for Brain Core."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from .contracts import BrainAnalysis, BrainTaskContext


class BrainAnalysisModule(Protocol):
    """Contract for Brain Core analysis modules."""

    name: str
    description: str
    supported_modes: tuple[str, ...]

    def supports(self, context: BrainTaskContext) -> bool: ...

    def analyze(self, context: BrainTaskContext) -> BrainAnalysis: ...


class BrainModuleDescriptor(BaseModel):
    name: str
    description: str
    supported_modes: list[str] = Field(default_factory=list)


class BrainModuleRegistry:
    """Hold analysis modules and expose a stable iteration surface."""

    def __init__(self, modules: list[BrainAnalysisModule]):
        self._modules = modules

    def list_descriptors(self) -> list[BrainModuleDescriptor]:
        return [
            BrainModuleDescriptor(
                name=module.name,
                description=module.description,
                supported_modes=list(module.supported_modes),
            )
            for module in self._modules
        ]

    def iter_supported(self, context: BrainTaskContext) -> list[BrainAnalysisModule]:
        return [module for module in self._modules if module.supports(context)]
