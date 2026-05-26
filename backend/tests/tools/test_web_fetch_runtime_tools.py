from __future__ import annotations

import asyncio

import httpx


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


def test_runtime_web_fetch_tool_invokes_tls_fallback(monkeypatch) -> None:
    from src.community.ddg import tools as ddg_tools
    from src.community.tavily import tools as tavily_tools

    def fake_fetch_raw(url: str, timeout: float) -> tuple[int, str, str]:
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate")

    def fake_fetch_raw_without_verification(url: str, timeout: float) -> tuple[int, str, str]:
        assert url == "https://example.com/broken-chain"
        return 200, "text/html", "<html><head><title>Recovered</title></head><body><main>Recovered via web_fetch fallback.</main></body></html>"

    monkeypatch.setattr(tavily_tools, "_client", lambda: (_ for _ in ()).throw(RuntimeError("tavily unavailable")))
    monkeypatch.setattr(ddg_tools, "_fetch_raw", fake_fetch_raw)
    monkeypatch.setattr(ddg_tools, "_fetch_raw_without_verification", fake_fetch_raw_without_verification)

    result = asyncio.run(_available_tool("web_fetch").ainvoke({"url": "https://example.com/broken-chain"}))

    assert "TLS certificate verification failed" in result
    assert "Recovered" in result


def test_runtime_scrapling_fetch_tool_invokes_tls_fallback(monkeypatch) -> None:
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
        @staticmethod
        def get(url: str, **kwargs):
            assert url == "https://example.com/broken-chain"
            if kwargs.get("verify") is False:
                return FakePage()
            raise RuntimeError("curl: (60) SSL certificate problem: unable to get local issuer certificate")

    monkeypatch.setattr(scrapling_tools, "_INIT_TRIED", True)
    monkeypatch.setattr(scrapling_tools, "_FETCHER", FakeFetcher)

    result = _available_tool("scrapling_fetch").invoke({"url": "https://example.com/broken-chain"})

    assert "disabled_after_certificate_error" in result
    assert "Recovered via scrapling fallback" in result
