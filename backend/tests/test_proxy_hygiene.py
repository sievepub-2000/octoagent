import os
from contextlib import AbstractContextManager
from typing import Any

from scripts import run_tools_hub_registration_smoke


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient(AbstractContextManager):
    captured_kwargs: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        type(self).captured_kwargs = kwargs
        self._skill_name = ""
        self._deleted = False

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, path: str, *, json: dict[str, Any]) -> _FakeResponse:
        self._skill_name = str(json["name"])
        return _FakeResponse({"name": self._skill_name})

    def get(self, path: str) -> _FakeResponse:
        if path == "/api/tools/registry":
            skills = [] if self._deleted else [{"name": self._skill_name}]
            return _FakeResponse({"skills": skills, "summary": {"skills_total": len(skills)}})
        raise AssertionError(f"Unexpected GET {path}")

    def delete(self, path: str) -> _FakeResponse:
        self._deleted = True
        return _FakeResponse({"success": True})


def test_tools_hub_smoke_ignores_proxy_environment(monkeypatch):
    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7890/")
    monkeypatch.setenv("all_proxy", "socks://127.0.0.1:7890/")
    monkeypatch.setattr(run_tools_hub_registration_smoke.httpx, "Client", _FakeClient)

    report = run_tools_hub_registration_smoke.run(gateway_url="http://127.0.0.1:19880")

    assert report.ok is True
    assert _FakeClient.captured_kwargs["trust_env"] is False
    assert os.environ["ALL_PROXY"] == "socks://127.0.0.1:7890/"
