#!/usr/bin/env python3
"""Minimal bridge relay for OctoAgent bridge-backed channels.

Run it with environment variables:

- OCTO_BASE_URL=http://127.0.0.1:19800
- BRIDGE_SHARED_SECRET=change-me
- LISTEN_HOST=127.0.0.1
- LISTEN_PORT=19814

Inbound upstream events should be normalized and posted to:

- POST /<platform>/inbound

OctoAgent outbound callbacks should target:

- POST /outbound
"""

from __future__ import annotations

import http.client
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


OCTO_BASE_URL = os.environ.get("OCTO_BASE_URL", "http://127.0.0.1:19800").rstrip("/")
BRIDGE_SHARED_SECRET = os.environ.get("BRIDGE_SHARED_SECRET", "change-me")
LISTEN_HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "19814"))
_PLATFORM_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


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


def _octo_connection() -> tuple[http.client.HTTPConnection, str]:
    parsed = urlparse(OCTO_BASE_URL)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("OCTO_BASE_URL must be an http(s) URL with a host")
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    base_path = parsed.path.rstrip("/")
    return connection_cls(parsed.hostname, parsed.port, timeout=15), base_path


def _forward_to_octoagent(platform: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    if not _PLATFORM_RE.fullmatch(platform):
        return 400, {"error": "invalid_platform"}
    body = json.dumps(payload).encode("utf-8")
    try:
        connection, base_path = _octo_connection()
        connection.request(
            "POST",
            f"{base_path}/api/channels/{platform}/ingest",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "X-OctoAgent-Bridge-Token": BRIDGE_SHARED_SECRET,
            },
        )
        response = connection.getresponse()
        data = response.read().decode("utf-8") or "{}"
        connection.close()
        return response.status, json.loads(data)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
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
