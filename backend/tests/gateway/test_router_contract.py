from __future__ import annotations

import pytest
from fastapi import APIRouter

from src.gateway.router_contract import build_router_contract, validate_router_contract


def test_router_contract_lists_paths_methods_and_tags() -> None:
    router = APIRouter(prefix="/api/demo", tags=["demo"])

    @router.get("/items")
    def list_items() -> dict[str, bool]:
        return {"ok": True}

    [contract] = build_router_contract([router])

    assert contract.prefix == "/api/demo"
    assert contract.tags == ("demo",)
    assert contract.routes[0].path == "/api/demo/items"
    assert contract.routes[0].methods == ("GET",)


def test_router_contract_rejects_duplicate_method_paths() -> None:
    first = APIRouter(prefix="/api/demo", tags=["demo"])
    second = APIRouter(prefix="/api/demo", tags=["demo"])

    @first.get("/items")
    def list_items() -> dict[str, bool]:
        return {"ok": True}

    @second.get("/items")
    def list_items_again() -> dict[str, bool]:
        return {"ok": True}

    with pytest.raises(RuntimeError, match="duplicate routes"):
        validate_router_contract([first, second])
