"""High-level OctoAgent HTTP API client for external consumers."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class OctoAgentHTTPClient:
    """Sync HTTP client for the OctoAgent REST API.

    Uses only stdlib so the SDK has zero external dependencies.
    """

    def __init__(self, base_url: str, token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, data: dict | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode() if data else None
        req = Request(url, data=body, headers=self._headers(), method=method)
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as exc:
            logger.error("HTTP %s %s → %d", method, path, exc.code)
            raise

    # ------------------------------------------------------------------
    # Workspace operations
    # ------------------------------------------------------------------

    def list_workspaces(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/workspaces")

    def get_workspace(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/workspaces/{task_id}")

    def create_workspace(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/workspaces", payload)

    # ------------------------------------------------------------------
    # Agent operations
    # ------------------------------------------------------------------

    def list_agents(self, task_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/workspaces/{task_id}/agents")

    def send_message(self, task_id: str, agent_id: str, content: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/workspaces/{task_id}/agents/{agent_id}/messages",
            {"content": content},
        )

    # ------------------------------------------------------------------
    # Capability operations
    # ------------------------------------------------------------------

    def get_capabilities(self) -> dict[str, Any]:
        return self._request("GET", "/api/capabilities/inventory")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/api/health")
