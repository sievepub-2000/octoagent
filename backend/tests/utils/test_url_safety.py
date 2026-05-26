from __future__ import annotations

import socket

import pytest

from src.utils.url_safety import is_url_safe, safe_join_url


def _addrinfo(address: str):
    return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


def test_is_url_safe_blocks_if_any_resolved_address_is_private(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return _addrinfo("93.184.216.34") + _addrinfo("10.0.0.4")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    assert is_url_safe("https://example.com/page") is False


def test_is_url_safe_allows_public_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return _addrinfo("93.184.216.34")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    assert is_url_safe("https://example.com/page") is True


def test_safe_join_url_blocks_private_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(hostname: str, *args, **kwargs):
        if hostname == "internal.example":
            return _addrinfo("127.0.0.1")
        return _addrinfo("93.184.216.34")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    assert safe_join_url("https://example.com/start", "https://internal.example/admin") is None
