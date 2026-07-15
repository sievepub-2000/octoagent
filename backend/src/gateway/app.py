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
        version="20260715",
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

    _persistence_cache: dict = {"ts": 0.0, "data": None}
    _persistence_ttl = 30.0

    def _probe_persistence() -> dict:
        """Best-effort LangGraph checkpoint persistence probe (cached, never raises)."""
        import time as _time

        now = _time.monotonic()
        cached = _persistence_cache.get("data")
        if cached is not None and (now - _persistence_cache["ts"]) < _persistence_ttl:
            return cached
        result: dict = {"backend": "unknown", "ok": False}
        try:
            from src.runtime.config.app_config import get_app_config

            cfg = getattr(get_app_config(), "checkpointer", None)
            ctype = getattr(cfg, "type", None) if cfg else None
            dsn = getattr(cfg, "connection_string", None) if cfg else None
            if ctype != "postgres" or not dsn:
                result = {"backend": ctype or "memory", "ok": cfg is not None}
            else:
                import psycopg

                with psycopg.connect(dsn, connect_timeout=2) as conn, conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM checkpoints")
                    checkpoints = int(cur.fetchone()[0])
                    cur.execute("SELECT count(DISTINCT thread_id) FROM checkpoints")
                    threads = int(cur.fetchone()[0])
                result = {
                    "backend": "postgres",
                    "ok": True,
                    "checkpoints": checkpoints,
                    "threads": threads,
                }
        except Exception as exc:  # noqa: BLE001 - health probe must never raise
            result = {"backend": "postgres", "ok": False, "error": str(exc)[:200]}
        _persistence_cache["data"] = result
        _persistence_cache["ts"] = now
        return result

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """Health check endpoint.

        Returns:
            Service health status information, including a cached LangGraph
            checkpoint persistence summary.
        """
        import asyncio

        persistence = await asyncio.to_thread(_probe_persistence)
        return {"status": "healthy", "service": "octoagent-gateway", "persistence": persistence}

    @app.get("/health/persistence", tags=["health"])
    async def health_persistence() -> dict:
        """LangGraph checkpoint persistence detail (cached 30s, never raises)."""
        import asyncio

        return await asyncio.to_thread(_probe_persistence)

    return app


# Create app instance for uvicorn
app = create_app()
