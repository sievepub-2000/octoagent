"""Atomic JSON write utility.

Writes JSON data to a file atomically by writing to a temporary file first,
then renaming into place. This prevents data corruption if the process crashes
or is killed mid-write.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(
    path: str | Path,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    """Write *data* as JSON to *path* atomically.

    Writes to a sibling temporary file and renames it over the target, so
    readers always see either the old complete file or the new complete file —
    never a partially-written file.

    Args:
        path: Destination file path.
        data: JSON-serialisable object.
        indent: JSON indentation level (default 2).
        ensure_ascii: Whether to escape non-ASCII characters (default False).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        target_stat = path.stat()
        target_mode = target_stat.st_mode & 0o777
    except FileNotFoundError:
        target_stat = path.parent.stat()
        target_mode = (target_stat.st_mode & 0o666) or 0o600
    target_uid = target_stat.st_uid
    target_gid = target_stat.st_gid

    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, target_mode)
        try:
            os.chown(tmp_path, target_uid, target_gid)
        except (AttributeError, PermissionError, OSError):
            pass
        os.replace(tmp_path, path)  # atomic on POSIX (and near-atomic on Windows)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
