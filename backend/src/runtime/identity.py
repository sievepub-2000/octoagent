"""Cross-platform runtime identity.

Single, portable definition of the OS user that the OctoAgent runtime should
operate as, plus the per-OS data/config/cache roots.  Works on Linux, macOS,
and Windows.

Design contract:
- The runtime always operates as the OS user that launched the process.
- File ownership semantics (`chown`) are only enforced on POSIX systems; on
  Windows they are silently skipped because NTFS uses ACLs instead.
- No application code path should call `sudo` / `runas` itself.  Privilege
  elevation, if needed, must happen in the install script before the daemon
  starts.
"""

from __future__ import annotations

import getpass
import logging
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


def _safe_getuid() -> int | None:
    return None if IS_WINDOWS else os.getuid()  # type: ignore[attr-defined]


def _safe_getgid() -> int | None:
    return None if IS_WINDOWS else os.getgid()  # type: ignore[attr-defined]


def _safe_geteuid() -> int | None:
    return None if IS_WINDOWS else os.geteuid()  # type: ignore[attr-defined]


class _PosixUser(NamedTuple):
    username: str
    home: Path


def _resolve_posix_user() -> _PosixUser | None:
    """Resolve the real runtime user from the effective POSIX uid."""
    if IS_WINDOWS:
        return None
    uid = _safe_geteuid()
    if uid is None:
        uid = _safe_getuid()
    if uid is None:
        return None
    try:
        import pwd  # POSIX-only

        entry = pwd.getpwuid(uid)
    except Exception:
        return None
    return _PosixUser(username=entry.pw_name, home=Path(entry.pw_dir).expanduser().resolve())


def _resolve_username() -> str:
    if posix_user := _resolve_posix_user():
        return posix_user.username
    for env_key in ("SUDO_USER", "USER", "USERNAME", "LOGNAME"):
        value = os.environ.get(env_key)
        if value:
            return value
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover
        return "octoagent"


def _resolve_home() -> Path:
    if env_home := os.environ.get("OCTO_AGENT_HOME"):
        return Path(env_home).expanduser().resolve()
    if posix_user := _resolve_posix_user():
        return posix_user.home
    return Path.home().resolve()


def _xdg_root(env_key: str, home: Path) -> Path | None:
    raw = os.environ.get(env_key)
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    try:
        resolved = candidate.resolve()
    except Exception:
        resolved = candidate.absolute()
    if not IS_WINDOWS and home != Path("/root") and resolved == Path("/root"):
        return None
    if not IS_WINDOWS and home != Path("/root") and Path("/root") in resolved.parents:
        return None
    return resolved


def _default_data_root(home: Path) -> Path:
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA")
        return Path(appdata) / "octoagent" if appdata else home / "AppData" / "Roaming" / "octoagent"
    if IS_MACOS:
        return home / "Library" / "Application Support" / "octoagent"
    xdg = _xdg_root("XDG_DATA_HOME", home)
    return xdg / "octoagent" if xdg else home / ".local" / "share" / "octoagent"


def _default_config_root(home: Path) -> Path:
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA")
        return (Path(appdata) / "octoagent" / "config") if appdata else home / "AppData" / "Roaming" / "octoagent" / "config"
    if IS_MACOS:
        return home / "Library" / "Application Support" / "octoagent" / "config"
    xdg = _xdg_root("XDG_CONFIG_HOME", home)
    return xdg / "octoagent" if xdg else home / ".config" / "octoagent"


def _default_cache_root(home: Path) -> Path:
    if IS_WINDOWS:
        local_appdata = os.environ.get("LOCALAPPDATA")
        return (Path(local_appdata) / "octoagent" / "cache") if local_appdata else home / "AppData" / "Local" / "octoagent" / "cache"
    if IS_MACOS:
        return home / "Library" / "Caches" / "octoagent"
    xdg = _xdg_root("XDG_CACHE_HOME", home)
    return xdg / "octoagent" if xdg else home / ".cache" / "octoagent"


@dataclass(frozen=True)
class RuntimeIdentity:
    username: str
    home: Path
    data_root: Path
    config_root: Path
    cache_root: Path
    uid: int | None
    gid: int | None
    euid: int | None
    platform: str
    can_chown: bool
    is_root: bool

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "home": str(self.home),
            "data_root": str(self.data_root),
            "config_root": str(self.config_root),
            "cache_root": str(self.cache_root),
            "uid": self.uid,
            "gid": self.gid,
            "euid": self.euid,
            "platform": self.platform,
            "can_chown": self.can_chown,
            "is_root": self.is_root,
        }


_cached: RuntimeIdentity | None = None


def get_runtime_identity() -> RuntimeIdentity:
    global _cached
    if _cached is not None:
        return _cached
    home = _resolve_home()
    uid = _safe_getuid()
    gid = _safe_getgid()
    euid = _safe_geteuid()
    _cached = RuntimeIdentity(
        username=_resolve_username(),
        home=home,
        data_root=_default_data_root(home),
        config_root=_default_config_root(home),
        cache_root=_default_cache_root(home),
        uid=uid,
        gid=gid,
        euid=euid,
        platform=platform.system(),
        can_chown=not IS_WINDOWS,
        is_root=(euid == 0) if euid is not None else False,
    )
    logger.info(
        "runtime identity: user=%s platform=%s home=%s data_root=%s can_chown=%s",
        _cached.username,
        _cached.platform,
        _cached.home,
        _cached.data_root,
        _cached.can_chown,
    )
    return _cached


def reset_runtime_identity_cache() -> None:
    global _cached
    _cached = None
