from __future__ import annotations

from types import SimpleNamespace

from src.runtime import permissions as runtime_permissions


def test_target_uid_gid_uses_runtime_identity_over_sudo_env(monkeypatch) -> None:
    monkeypatch.setattr(runtime_permissions, "IS_WINDOWS", False)
    monkeypatch.setenv("SUDO_UID", "0")
    monkeypatch.setenv("SUDO_GID", "0")
    monkeypatch.setattr(
        runtime_permissions,
        "get_runtime_identity",
        lambda: SimpleNamespace(uid=1000, gid=1000),
    )

    assert runtime_permissions._target_uid_gid() == (1000, 1000)
