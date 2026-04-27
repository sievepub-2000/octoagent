import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.gateway.config import get_gateway_config
from src.gateway.lifecycle import gateway_lifespan
from src.gateway.metadata import API_DESCRIPTION, OPENAPI_TAGS
from src.gateway.router_registry import register_routers
from src.utils.logging_config import setup_logging

# Configure logging (centralized: console + rotating file handler)
setup_logging()

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """

    gateway_cfg = get_gateway_config()

    app = FastAPI(
        title="OctoAgent API Gateway",
        description=API_DESCRIPTION,
        version="3.0.3",
        lifespan=gateway_lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=OPENAPI_TAGS,
    )

    # Rate limiting
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Please try again later."},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=gateway_cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

    register_routers(app)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """Health check endpoint.

        Returns:
            Service health status information.
        """
        return {"status": "healthy", "service": "octoagent-gateway"}

    return app


# Create app instance for uvicorn
app = create_app()
