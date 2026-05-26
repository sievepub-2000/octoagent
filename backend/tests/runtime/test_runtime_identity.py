from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from src.runtime import identity as runtime_identity


def test_runtime_identity_prefers_effective_posix_uid_over_root_env(monkeypatch) -> None:
    runtime_identity.reset_runtime_identity_cache()
    monkeypatch.setattr(runtime_identity, "IS_WINDOWS", False)
    monkeypatch.setattr(runtime_identity, "IS_MACOS", False)
    monkeypatch.setattr(runtime_identity.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runtime_identity.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(runtime_identity.os, "getgid", lambda: 1000, raising=False)
    monkeypatch.setattr(runtime_identity.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setenv("USER", "root")
    monkeypatch.setenv("LOGNAME", "root")
    monkeypatch.setenv("HOME", "/root")
    monkeypatch.setenv("XDG_DATA_HOME", "/root/.local/share")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/root/.config")
    monkeypatch.setenv("XDG_CACHE_HOME", "/root/.cache")

    fake_pwd = SimpleNamespace(
        getpwuid=lambda uid: SimpleNamespace(
            pw_name="sieve-pub",
            pw_dir="/home/sieve-pub",
        )
    )
    monkeypatch.setitem(sys.modules, "pwd", fake_pwd)

    identity = runtime_identity.get_runtime_identity()

    assert identity.username == "sieve-pub"
    assert identity.home == Path("/home/sieve-pub")
    assert identity.data_root == Path("/home/sieve-pub/.local/share/octoagent")
    assert identity.config_root == Path("/home/sieve-pub/.config/octoagent")
    assert identity.cache_root == Path("/home/sieve-pub/.cache/octoagent")
    assert identity.is_root is False
    runtime_identity.reset_runtime_identity_cache()
