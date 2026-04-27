"""Async OctoAgent HTTP API client for consumers that need non-blocking I/O.

Uses only stdlib (asyncio + urllib) so the SDK remains zero-dependency.
For production use, ``httpx`` or ``aiohttp`` can replace the executor
call for better connection pooling.
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Shared executor for async HTTP calls (stdlib has no native async HTTP)
_executor = ThreadPoolExecutor(max_workers=4)


class OctoAgentAsyncClient:
    """Async HTTP client for the OctoAgent REST API.

    Wraps stdlib ``urllib`` in an executor to provide async/await
    interface without adding external dependencies.
    """

    def __init__(self, base_url: str, token: str | None = None, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _sync_request(self, method: str, path: str, data: dict | None = None) -> dict[str, Any]:
        """Blocking HTTP request (called inside executor)."""
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode() if data else None
        req = Request(url, data=body, headers=self._headers(), method=method)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as exc:
            logger.error("HTTP %s %s → %d", method, path, exc.code)
            raise

    async def _request(self, method: str, path: str, data: dict | None = None) -> dict[str, Any]:
        """Non-blocking HTTP request via executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, self._sync_request, method, path, data)

    # ------------------------------------------------------------------
    # Workspace operations
    # ------------------------------------------------------------------

    async def list_workspaces(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/workspaces")

    async def get_workspace(self, task_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/workspaces/{task_id}")

    async def create_workspace(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/api/workspaces", payload)

    # ------------------------------------------------------------------
    # Agent operations
    # ------------------------------------------------------------------

    async def list_agents(self, task_id: str) -> list[dict[str, Any]]:
        return await self._request("GET", f"/api/workspaces/{task_id}/agents")

    async def send_message(self, task_id: str, agent_id: str, content: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/api/workspaces/{task_id}/agents/{agent_id}/messages",
            {"content": content},
        )

    # ------------------------------------------------------------------
    # Capability operations
    # ------------------------------------------------------------------

    async def get_capabilities(self) -> dict[str, Any]:
        return await self._request("GET", "/api/capabilities/inventory")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/api/health")

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> OctoAgentAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass
