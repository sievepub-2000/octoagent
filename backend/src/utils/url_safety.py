"""URL safety validation utilities for SSRF protection."""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

_BLOCKED_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "[::1]",
    "metadata.google.internal",
    "169.254.169.254",
}


def _is_public_ip(address: str) -> bool:
    ip_obj = ipaddress.ip_address(address)
    return not (ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_unspecified)


def safe_join_url(base_url: str, next_url: str) -> str | None:
    """Resolve a redirect target and return it only if it is fetch-safe."""
    if not next_url:
        return None
    candidate = urljoin(base_url, next_url)
    return candidate if is_url_safe(candidate) else None


def is_url_safe(url: str) -> bool:
    """Check if a URL is safe to fetch (not targeting private/internal networks).

    Args:
        url: The URL to validate.

    Returns:
        True if the URL targets a public address, False if it targets private/internal networks.
    """
    if not url or not url.startswith(("http://", "https://")):
        return False

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False

        if hostname.lower() in _BLOCKED_HOSTNAMES:
            return False

        resolved_addresses = {result[4][0] for result in socket.getaddrinfo(hostname, parsed.port, type=socket.SOCK_STREAM)}
        if not resolved_addresses:
            return False

        for resolved_ip in resolved_addresses:
            if not _is_public_ip(resolved_ip):
                logger.warning("Blocked SSRF attempt to private IP %s (hostname: %s)", resolved_ip, hostname)
                return False

        return True
    except (socket.gaierror, ValueError, OSError) as exc:
        logger.warning("URL safety check failed for %s: %s", url, exc)
        return False
