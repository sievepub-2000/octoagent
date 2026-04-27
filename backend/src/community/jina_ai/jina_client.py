import logging
import os

import requests

logger = logging.getLogger(__name__)

_JINA_AVAILABLE: bool | None = None  # None = untested, True/False = cached result


def _check_jina_available(connect_timeout: float) -> bool:
    """Probe r.jina.ai reachability; cache the result to avoid repeated hangs."""
    global _JINA_AVAILABLE
    if _JINA_AVAILABLE is not None:
        return _JINA_AVAILABLE
    try:
        requests.head("https://r.jina.ai/", timeout=(connect_timeout, 3))
        _JINA_AVAILABLE = True
    except Exception:
        _JINA_AVAILABLE = False
    return _JINA_AVAILABLE


def _direct_fetch(url: str, timeout: int) -> str:
    """Fallback: fetch the target URL directly and return raw HTML."""
    direct_headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; OctoAgentBot/1.0; +https://github.com/octoagent)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    response = requests.get(url, headers=direct_headers, timeout=(5, timeout), allow_redirects=True)
    response.raise_for_status()
    return response.text


class JinaClient:
    def crawl(self, url: str, return_format: str = "html", timeout: int = 10) -> str:
        connect_timeout = min(max(timeout, 3), 8)
        read_timeout = min(max(timeout, 5), 30)

        # Try Jina reader only if known reachable; use a short connect probe to avoid hangs.
        if _check_jina_available(connect_timeout=3):
            headers = {
                "Content-Type": "application/json",
                "X-Return-Format": return_format,
                "X-Timeout": str(timeout),
            }
            if os.getenv("JINA_API_KEY"):
                headers["Authorization"] = f"Bearer {os.getenv('JINA_API_KEY')}"
            else:
                logger.warning(
                    "Jina API key is not set. Provide your own key to access a higher rate limit. "
                    "See https://jina.ai/reader for more information."
                )
            data = {"url": url}
            try:
                response = requests.post(
                    "https://r.jina.ai/",
                    headers=headers,
                    json=data,
                    timeout=(connect_timeout, read_timeout),
                )
                if response.status_code == 200 and response.text and response.text.strip():
                    return response.text
                error_message = f"Jina API returned status {response.status_code}: {response.text[:200]}"
                logger.error(error_message)
                # Fall through to direct fetch
            except Exception as e:
                logger.warning("Jina fetch failed (%s); falling back to direct HTTP fetch.", e)
                global _JINA_AVAILABLE
                _JINA_AVAILABLE = False  # avoid future probes this session
        else:
            logger.info("Jina reader not reachable; using direct HTTP fetch for %s", url)

        # --- Direct HTTP fallback ---
        try:
            html_content = _direct_fetch(url, timeout=read_timeout)
            if html_content and html_content.strip():
                return html_content
            return "Error: Direct fetch returned empty response"
        except Exception as e:
            error_message = f"Both Jina and direct fetch failed for {url}: {str(e)}"
            logger.error(error_message)
            return f"Error: {error_message}"
