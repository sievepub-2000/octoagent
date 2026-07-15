from __future__ import annotations

import json

import pytest

from src.community.scrapling import tools as scrapling_tools


@pytest.fixture(autouse=True)
def allow_example_urls(monkeypatch) -> None:
    original = scrapling_tools.is_url_safe
    monkeypatch.setattr(
        scrapling_tools,
        "is_url_safe",
        lambda url: (True, "") if "example.com" in url else original(url),
    )


class _FakeSelection(list):
    def get(self) -> str:
        return self[0]


class _FakePage:
    def css(self, selector: str) -> _FakeSelection:
        assert selector == "title::text"
        return _FakeSelection(["Recovered title"])

    def get_all_text(self, *, strip: bool = False) -> str:
        return "Recovered scrapling content"


class _FakeFetcher:
    calls: list[dict[str, object]] = []

    @classmethod
    def get(cls, url: str, **kwargs: object) -> _FakePage:
        cls.calls.append(kwargs)
        if kwargs.get("verify") is False:
            return _FakePage()
        raise RuntimeError("Failed to perform, curl: (60) SSL certificate problem: unable to get local issuer certificate")


def test_scrapling_fetch_retries_public_cert_chain_failures(monkeypatch) -> None:
    _FakeFetcher.calls = []
    monkeypatch.setenv("OCTO_SCRAPLING_ALLOW_INSECURE_SSL_RETRY", "1")
    monkeypatch.setattr(scrapling_tools, "_INIT_TRIED", True)
    monkeypatch.setattr(scrapling_tools, "_FETCHER", _FakeFetcher)

    result = scrapling_tools.scrapling_fetch.invoke({"url": "https://example.com/broken-chain"})
    parsed = json.loads(result)

    assert parsed["content"] == "Recovered scrapling content"
    assert parsed["title"] == "Recovered title"
    assert parsed["tls_verification"] == "disabled_after_certificate_error"
    assert _FakeFetcher.calls[-1]["verify"] is False


def test_scrapling_fetch_rejects_private_urls(monkeypatch) -> None:
    monkeypatch.setattr(scrapling_tools, "_INIT_TRIED", True)
    monkeypatch.setattr(scrapling_tools, "_FETCHER", _FakeFetcher)

    result = scrapling_tools.scrapling_fetch.invoke({"url": "http://127.0.0.1:19804/docs"})
    parsed = json.loads(result)

    assert parsed["engine"] == "scrapling"
    assert "private/internal" in parsed["error"]


def test_scrapling_stealth_rejects_private_urls(monkeypatch) -> None:
    monkeypatch.setattr(scrapling_tools, "_INIT_TRIED", True)
    monkeypatch.setattr(scrapling_tools, "_STEALTHY", object())

    result = scrapling_tools.scrapling_fetch_stealth.invoke({"url": "http://localhost:19804/docs"})
    parsed = json.loads(result)

    assert parsed["engine"] == "scrapling"
    assert "private/internal" in parsed["error"]
