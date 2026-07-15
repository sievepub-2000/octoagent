from __future__ import annotations

import asyncio

import httpx
import pytest

from src.community.ddg import tools as ddg_tools
from src.community.scrapling import tools as scrapling_tools


@pytest.fixture(autouse=True)
def allow_example_urls(monkeypatch) -> None:
    ddg_original = ddg_tools.is_url_safe
    scrapling_original = scrapling_tools.is_url_safe
    monkeypatch.setattr(
        ddg_tools,
        "is_url_safe",
        lambda url: (True, "") if "example.com" in url else ddg_original(url),
    )
    monkeypatch.setattr(
        scrapling_tools,
        "is_url_safe",
        lambda url: (True, "") if "example.com" in url else scrapling_original(url),
    )


def _available_tool(name: str):
    from src.tools import get_available_tools

    for tool in get_available_tools(include_mcp=False, permission_mode="approval"):
        if tool.name == name:
            return tool
    raise AssertionError(f"tool not available: {name}")


def test_runtime_exposes_web_fetch_and_scrapling_fetch() -> None:
    from src.tools import get_available_tools

    names = {tool.name for tool in get_available_tools(include_mcp=False, permission_mode="approval")}

    assert "web_fetch" in names
    assert "scrapling_fetch" in names


def test_runtime_web_fetch_refuses_implicit_tls_verification_bypass(monkeypatch) -> None:
    from src.community.ddg import tools as ddg_tools
    from src.community.tavily import tools as tavily_tools

    def fake_fetch_raw(url: str, timeout: float) -> tuple[int, str, str]:
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate")

    insecure_retry_called = False

    def fake_fetch_raw_without_verification(url: str, timeout: float) -> tuple[int, str, str]:
        nonlocal insecure_retry_called
        insecure_retry_called = True
        return 200, "text/html", "unsafe"

    monkeypatch.setattr(tavily_tools, "_client", lambda: (_ for _ in ()).throw(RuntimeError("tavily unavailable")))
    monkeypatch.setattr(ddg_tools, "_fetch_raw", fake_fetch_raw)
    monkeypatch.setattr(ddg_tools, "_fetch_raw_without_verification", fake_fetch_raw_without_verification)

    result = asyncio.run(_available_tool("web_fetch").ainvoke({"url": "https://example.com/broken-chain"}))

    assert "CERTIFICATE_VERIFY_FAILED" in result
    assert insecure_retry_called is False


def test_runtime_scrapling_fetch_refuses_implicit_tls_verification_bypass(monkeypatch) -> None:
    from src.community.scrapling import tools as scrapling_tools

    class FakeSelector:
        def get(self) -> str:
            return "Recovered Scrapling"

    class FakePage:
        def css(self, query: str) -> FakeSelector:
            assert query == "title::text"
            return FakeSelector()

        def get_all_text(self, strip: bool = True) -> str:
            return "Recovered via scrapling fallback."

    class FakeFetcher:
        insecure_retry_called = False

        @staticmethod
        def get(url: str, **kwargs):
            assert url == "https://example.com/broken-chain"
            if kwargs.get("verify") is False:
                FakeFetcher.insecure_retry_called = True
                return FakePage()
            raise RuntimeError("curl: (60) SSL certificate problem: unable to get local issuer certificate")

    monkeypatch.setattr(scrapling_tools, "_INIT_TRIED", True)
    monkeypatch.setattr(scrapling_tools, "_FETCHER", FakeFetcher)

    result = _available_tool("scrapling_fetch").invoke({"url": "https://example.com/broken-chain"})

    assert "SSL certificate problem" in result
    assert FakeFetcher.insecure_retry_called is False
