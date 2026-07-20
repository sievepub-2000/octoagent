from __future__ import annotations

import pytest

from src.gateway.routers import brain


@pytest.mark.asyncio
async def test_brain_capabilities_exposes_registered_modules() -> None:
    response = await brain.get_brain_capabilities()

    assert [module.name for module in response.modules] == [
        "research",
        "evidence_router",
        "memory_reasoner",
        "quant",
    ]
    assert response.supported_modes == ["plan", "research", "quant", "policy"]
    assert response.execution_backends == ["workflow_contracts"]
    assert "LangGraph" in response.notes[0]
