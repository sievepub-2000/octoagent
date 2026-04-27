import os

from pydantic import BaseModel, Field


class GatewayConfig(BaseModel):
    """Configuration for the API Gateway."""

    host: str = Field(default="0.0.0.0", description="Host to bind the gateway server")
    port: int = Field(default=19882, description="Port to bind the gateway server")
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:19886",
            "http://127.0.0.1:19886",
            "http://localhost:19880",
            "http://127.0.0.1:19880",
        ],
        description="Allowed CORS origins",
    )


_gateway_config: GatewayConfig | None = None


def get_gateway_config() -> GatewayConfig:
    """Get gateway config, loading from environment if available."""
    global _gateway_config
    if _gateway_config is None:
        frontend_port = os.getenv("OCTO_FRONTEND_PORT", "19886")
        ingress_port = os.getenv("OCTO_NGINX_PORT", "19880")
        cors_origins_str = os.getenv(
            "CORS_ORIGINS",
            ",".join([
                f"http://localhost:{frontend_port}",
                f"http://127.0.0.1:{frontend_port}",
                f"http://localhost:{ingress_port}",
                f"http://127.0.0.1:{ingress_port}",
            ]),
        )
        _gateway_config = GatewayConfig(
            host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
            port=int(os.getenv("GATEWAY_PORT", os.getenv("OCTO_GATEWAY_PORT", "19882"))),
            cors_origins=cors_origins_str.split(","),
        )
    return _gateway_config
