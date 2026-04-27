"""URL safety validation utilities for SSRF protection."""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


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

        # Block common internal hostnames
        blocked_hostnames = {
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "::1",
            "[::1]",
            "metadata.google.internal",
            "169.254.169.254",
        }
        if hostname.lower() in blocked_hostnames:
            return False

        # Resolve hostname and check IP range
        resolved_ip = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(resolved_ip)

        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_reserved
            or ip_obj.is_link_local
            or ip_obj.is_multicast
        ):
            logger.warning("Blocked SSRF attempt to private IP %s (hostname: %s)", resolved_ip, hostname)
            return False

        return True
    except (socket.gaierror, ValueError, OSError) as exc:
        logger.warning("URL safety check failed for %s: %s", url, exc)
        return False
