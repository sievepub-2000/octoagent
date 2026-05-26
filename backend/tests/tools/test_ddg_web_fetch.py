from __future__ import annotations

import httpx

from src.community.ddg import tools as ddg_tools


def test_ddg_web_fetch_supports_sync_invoke(monkeypatch) -> None:
    def fake_fetch_raw(url: str, timeout: float) -> tuple[int, str, str]:
        assert url == "https://example.com/article"
        assert timeout > 0
        return 200, "text/html", "<html><body><main><h1>Title</h1><p>Readable article text.</p></main></body></html>"

    monkeypatch.setattr(ddg_tools, "_fetch_raw", fake_fetch_raw)

    result = ddg_tools.web_fetch_tool.invoke({"url": "https://example.com/article"})

    assert isinstance(result, str)
    assert "StructuredTool does not support sync invocation" not in result
    assert "Readable article text" in result or "Raw HTML" in result


def test_ddg_web_fetch_retries_public_cert_chain_failures(monkeypatch) -> None:
    def fake_fetch_raw(url: str, timeout: float) -> tuple[int, str, str]:
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate")

    def fake_fetch_raw_without_verification(url: str, timeout: float) -> tuple[int, str, str]:
        assert url == "https://example.com/broken-chain"
        return 200, "text/html", "<html><body><main><h1>Recovered</h1><p>Recovered over TLS fallback.</p></main></body></html>"

    monkeypatch.setattr(ddg_tools, "_fetch_raw", fake_fetch_raw)
    monkeypatch.setattr(ddg_tools, "_fetch_raw_without_verification", fake_fetch_raw_without_verification)

    result = ddg_tools.web_fetch_tool.invoke({"url": "https://example.com/broken-chain"})

    assert "TLS certificate verification failed" in result
    assert "Recovered over TLS fallback" in result or "Raw HTML" in result
