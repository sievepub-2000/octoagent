"""Helpers for safely using proxy environment variables.

Local deployments often inherit HTTP(S)_PROXY from an operator shell. If that
proxy points at localhost but the proxy process is not running, web tools should
fall back to direct egress instead of failing every request with connection
refused.
"""

from __future__ import annotations

import os
import socket
from contextlib import contextmanager
from urllib.parse import urlparse

_PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")
_LOCAL_PROXY_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _proxy_endpoint(value: str) -> tuple[str, int] | None:
    parsed = urlparse(value if "://" in value else f"http://{value}")
    if not parsed.hostname or parsed.port is None:
        return None
    return parsed.hostname, parsed.port


def _is_unavailable_local_proxy(value: str) -> bool:
    endpoint = _proxy_endpoint(value)
    if endpoint is None:
        return False
    host, port = endpoint
    if host.lower() not in _LOCAL_PROXY_HOSTS:
        return False
    try:
        with socket.create_connection((host, port), timeout=0.35):
            return False
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
