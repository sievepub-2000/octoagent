#!/usr/bin/env python3
"""Minimal bridge relay for OctoAgent bridge-backed channels.

Run it with environment variables:

- OCTO_BASE_URL=http://127.0.0.1:19880
- BRIDGE_SHARED_SECRET=change-me
- LISTEN_HOST=127.0.0.1
- LISTEN_PORT=30100

Inbound upstream events should be normalized and posted to:

- POST /<platform>/inbound

OctoAgent outbound callbacks should target:

- POST /outbound
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OCTO_BASE_URL = os.environ.get("OCTO_BASE_URL", "http://127.0.0.1:19880").rstrip("/")
BRIDGE_SHARED_SECRET = os.environ.get("BRIDGE_SHARED_SECRET", "change-me")
LISTEN_HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "30100"))


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    return json.loads(raw.decode("utf-8") or "{}")


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _forward_to_octoagent(platform: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    request = Request(
        url=f"{OCTO_BASE_URL}/api/channels/{platform}/ingest",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-OctoAgent-Bridge-Token": BRIDGE_SHARED_SECRET,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            data = response.read().decode("utf-8") or "{}"
            return response.status, json.loads(data)
    except HTTPError as exc:
        body = exc.read().decode("utf-8") or "{}"
        return exc.code, {"error": body}
    except URLError as exc:
        return 502, {"error": str(exc)}


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "OctoBridgeExample/1.0"

    def do_GET(self) -> None:
        if self.path == "/health":
            _write_json(self, 200, {"ok": True, "octo_base_url": OCTO_BASE_URL})
            return
        _write_json(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path == "/outbound":
            token = self.headers.get("X-OctoAgent-Bridge-Token", "")
            if token != BRIDGE_SHARED_SECRET:
                _write_json(self, 403, {"error": "invalid_bridge_token"})
                return
            payload = _read_json(self)
            print("[outbound]", json.dumps(payload, ensure_ascii=False), flush=True)
            _write_json(self, 200, {"accepted": True})
            return

        if self.path.count("/") == 2 and self.path.endswith("/inbound"):
            _, platform, _ = self.path.split("/")
            payload = _read_json(self)
            status, response = _forward_to_octoagent(platform, payload)
            _write_json(self, status, response)
            return

        _write_json(self, 404, {"error": "not_found"})


def main() -> None:
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), BridgeHandler)
    print(
        f"Bridge relay listening on http://{LISTEN_HOST}:{LISTEN_PORT} -> {OCTO_BASE_URL}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()