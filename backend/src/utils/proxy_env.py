"""Helpers for safely using proxy environment variables.

Local deployments often inherit HTTP(S)_PROXY from an operator shell. A local
proxy can accept TCP connections while all of its upstream nodes are dead, so a
port check alone is not enough.  Web tools probe a small HTTPS endpoint through
the proxy and fall back to direct egress when that end-to-end check fails.
"""

from __future__ import annotations

import os
import socket
import ssl
import time
from contextlib import contextmanager
from threading import Lock
from urllib.parse import urlparse
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

_PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")
_LOCAL_PROXY_HOSTS = {"127.0.0.1", "localhost", "::1"}
_HEALTH_CACHE: dict[str, tuple[float, bool]] = {}
_HEALTH_CACHE_LOCK = Lock()


def _proxy_endpoint(value: str) -> tuple[str, int] | None:
    parsed = urlparse(value if "://" in value else f"http://{value}")
    if not parsed.hostname or parsed.port is None:
        return None
    return parsed.hostname, parsed.port


def _probe_proxy_https(proxy_url: str) -> bool:
    health_url = os.getenv("OCTOAGENT_PROXY_HEALTH_URL", "https://www.gstatic.com/generate_204")
    try:
        timeout = max(0.5, float(os.getenv("OCTOAGENT_PROXY_HEALTH_TIMEOUT", "4")))
    except ValueError:
        timeout = 4.0
    opener = build_opener(
        ProxyHandler({"http": proxy_url, "https": proxy_url}),
        HTTPSHandler(context=ssl.create_default_context()),
    )
    try:
        with opener.open(Request(health_url, headers={"User-Agent": "OctoAgent/proxy-health"}), timeout=timeout) as response:
            return 200 <= response.status < 400
    except Exception:
        return False


def _proxy_https_healthy(value: str) -> bool:
    try:
        ttl = max(1.0, float(os.getenv("OCTOAGENT_PROXY_HEALTH_TTL", "30")))
    except ValueError:
        ttl = 30.0
    now = time.monotonic()
    with _HEALTH_CACHE_LOCK:
        cached = _HEALTH_CACHE.get(value)
        if cached and now - cached[0] < ttl:
            return cached[1]
    healthy = _probe_proxy_https(value)
    with _HEALTH_CACHE_LOCK:
        _HEALTH_CACHE[value] = (now, healthy)
    return healthy


def _is_unavailable_local_proxy(value: str) -> bool:
    endpoint = _proxy_endpoint(value)
    if endpoint is None:
        return False
    host, port = endpoint
    if host.lower() not in _LOCAL_PROXY_HOSTS:
        return False
    try:
        with socket.create_connection((host, port), timeout=0.35):
            return not _proxy_https_healthy(value)
    except OSError:
        return True


def has_unavailable_local_proxy() -> bool:
    return any(_is_unavailable_local_proxy(os.environ.get(key, "")) for key in _PROXY_KEYS)


def should_trust_proxy_env() -> bool:
    return not has_unavailable_local_proxy()


@contextmanager
def without_unavailable_local_proxy():
    if not has_unavailable_local_proxy():
        yield
        return
    saved = {key: os.environ.get(key) for key in _PROXY_KEYS}
    try:
        for key in _PROXY_KEYS:
            os.environ.pop(key, None)
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
