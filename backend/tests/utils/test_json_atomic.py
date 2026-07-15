from __future__ import annotations

import json
import os
import stat

from src.utils.json_atomic import write_json_atomic


def test_write_json_atomic_preserves_existing_file_mode(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o640)

    write_json_atomic(path, {"ok": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True}
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_write_json_atomic_inherits_parent_mode_for_new_file(tmp_path):
    tmp_path.chmod(0o750)
    path = tmp_path / "created.json"

    write_json_atomic(path, {"created": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"created": True}
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o640
