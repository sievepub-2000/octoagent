__all__ = ["AgentCoreService", "get_agent_core_service"]


def __getattr__(name: str):
	if name in {"AgentCoreService", "get_agent_core_service"}:
		from .service import AgentCoreService, get_agent_core_service

		return {
			"AgentCoreService": AgentCoreService,
			"get_agent_core_service": get_agent_core_service,
		}[name]
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")