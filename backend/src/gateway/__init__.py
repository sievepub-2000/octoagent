"""Gateway domain: FastAPI app, channels, monitoring, observability.

Lazy attribute access via PEP 562 to avoid pulling the full FastAPI app
when downstream modules (e.g. src.tools.builtins) only need
`src.gateway.observability`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .app import app, create_app  # noqa: F401
    from .config import GatewayConfig, get_gateway_config  # noqa: F401

__all__ = ["app", "create_app", "GatewayConfig", "get_gateway_config"]


def __getattr__(name: str) -> Any:
    if name in {"app", "create_app"}:
        from . import app as _app_mod

        return getattr(_app_mod, name)
    if name in {"GatewayConfig", "get_gateway_config"}:
        from . import config as _config_mod

        return getattr(_config_mod, name)
    raise AttributeError(f"module 'src.gateway' has no attribute {name!r}")
