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
    monkeypatch.setenv("OCTO_WEB_FETCH_ALLOW_INSECURE_SSL_RETRY", "1")
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


def test_ddg_web_fetch_does_not_disable_tls_verification_by_default(monkeypatch) -> None:
    monkeypatch.delenv("OCTO_WEB_FETCH_ALLOW_INSECURE_SSL_RETRY", raising=False)

    def fake_fetch_raw(url: str, timeout: float) -> tuple[int, str, str]:
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    def fail_if_called(url: str, timeout: float) -> tuple[int, str, str]:
        raise AssertionError("insecure TLS retry must be opt-in")

    monkeypatch.setattr(ddg_tools, "_fetch_raw", fake_fetch_raw)
    monkeypatch.setattr(ddg_tools, "_fetch_raw_without_verification", fail_if_called)

    result = ddg_tools.web_fetch_tool.invoke({"url": "https://example.com/broken-chain"})

    assert "CERTIFICATE_VERIFY_FAILED" in result


def test_ddg_web_fetch_retries_antibot_status_with_scrapling(monkeypatch) -> None:
    calls: list[tuple[str, str, bool]] = []

    def fake_fetch_raw(url: str, timeout: float) -> tuple[int, str, str]:
        assert url == "https://example.com/protected"
        return 403, "text/html", "<html><title>Forbidden</title><body>Access denied</body></html>"

    def fake_scrapling(url: str, *, reason: str, stealth: bool = False) -> str:
        calls.append((url, reason, stealth))
        return "# Recovered\n\nSource: https://example.com/protected\nEngine: scrapling\n\nRecovered protected article text."

    monkeypatch.setattr(ddg_tools, "_fetch_raw", fake_fetch_raw)
    monkeypatch.setattr(ddg_tools, "_scrapling_fallback_markdown", fake_scrapling)

    result = ddg_tools.web_fetch_tool.invoke({"url": "https://example.com/protected"})

    assert "Recovered protected article text" in result
    assert calls
    assert calls[0][0] == "https://example.com/protected"
    assert "HTTP status 403" in calls[0][1]


def test_ddg_web_fetch_retries_antibot_body_with_scrapling(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_fetch_raw(url: str, timeout: float) -> tuple[int, str, str]:
        return 200, "text/html", "<html><body><h1>Just a moment</h1><p>Cloudflare verify you are human.</p></body></html>"

    def fake_scrapling(url: str, *, reason: str, stealth: bool = False) -> str:
        calls.append((url, reason))
        return "# Recovered\n\nSource: https://example.com/challenge\nEngine: scrapling\n\nRecovered challenge article text."

    monkeypatch.setattr(ddg_tools, "_fetch_raw", fake_fetch_raw)
    monkeypatch.setattr(ddg_tools, "_scrapling_fallback_markdown", fake_scrapling)

    result = ddg_tools.web_fetch_tool.invoke({"url": "https://example.com/challenge"})

    assert "Recovered challenge article text" in result
    assert calls == [("https://example.com/challenge", "page content looks like an anti-bot, login, captcha, or JavaScript challenge")]
