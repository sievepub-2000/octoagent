"""Gateway router registration contract and validation."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter
from fastapi.routing import APIRoute


@dataclass(frozen=True)
class RouteContract:
    path: str
    methods: tuple[str, ...]
    name: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class RouterContract:
    prefix: str
    tags: tuple[str, ...]
    routes: tuple[RouteContract, ...]


@dataclass(frozen=True)
class RouterTagReport:
    routers: int
    routes: int
    missing_router_tags: tuple[str, ...]
    missing_route_tags: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_router_tags and not self.missing_route_tags


def build_router_contract(routers: list[APIRouter]) -> tuple[RouterContract, ...]:
    contracts: list[RouterContract] = []
    for router in routers:
        routes: list[RouteContract] = []
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            route_tags = tuple(str(tag) for tag in (route.tags or router.tags or ()))
            routes.append(
                RouteContract(
                    path=route.path,
                    methods=tuple(sorted(route.methods or ())),
                    name=route.name,
                    tags=route_tags,
                )
            )
        contracts.append(
            RouterContract(
                prefix=router.prefix,
                tags=tuple(str(tag) for tag in router.tags),
                routes=tuple(routes),
            )
        )
    return tuple(contracts)


def validate_router_contract(routers: list[APIRouter]) -> tuple[RouterContract, ...]:
    contracts = build_router_contract(routers)
    seen: dict[tuple[str, str], str] = {}
    duplicates: list[str] = []

    for contract in contracts:
        for route in contract.routes:
            for method in route.methods:
                key = (method, route.path)
                previous = seen.get(key)
                if previous is not None:
                    duplicates.append(f"{method} {route.path} ({previous}, {route.name})")
                else:
                    seen[key] = route.name

    if duplicates:
        raise RuntimeError("Invalid gateway router contract: duplicate routes: " + "; ".join(sorted(duplicates)))
    return contracts


def build_router_tag_report(routers: list[APIRouter]) -> RouterTagReport:
    contracts = build_router_contract(routers)
    missing_router_tags: list[str] = []
    missing_route_tags: list[str] = []
    route_count = 0
    for contract in contracts:
        if not contract.tags:
            missing_router_tags.append(contract.prefix or "<root>")
        for route in contract.routes:
            route_count += 1
            if not route.tags:
                methods = ",".join(route.methods)
                missing_route_tags.append(f"{methods} {route.path}")
    return RouterTagReport(
        routers=len(contracts),
        routes=route_count,
        missing_router_tags=tuple(sorted(set(missing_router_tags))),
        missing_route_tags=tuple(sorted(set(missing_route_tags))),
    )


def validate_router_tags(routers: list[APIRouter]) -> RouterTagReport:
    report = build_router_tag_report(routers)
    if not report.ok:
        raise RuntimeError(f"Invalid gateway router tags: missing_router_tags={list(report.missing_router_tags)} missing_route_tags={list(report.missing_route_tags)}")
    return report
