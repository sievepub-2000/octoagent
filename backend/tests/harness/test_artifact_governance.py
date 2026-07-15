from __future__ import annotations

import os
import time
from pathlib import Path

from src.harness.artifact_governance import cleanup_artifacts


def _age(path: Path, days: int) -> None:
    timestamp = time.time() - days * 86400
    os.utime(path, (timestamp, timestamp))


def test_cleanup_removes_only_explicit_disposable_roots(tmp_path: Path) -> None:
    old_tmp = tmp_path / "tmp" / "old.tmp"
    old_artifact = tmp_path / "runtime" / "system_tools" / "demo" / "artifacts" / "old.txt"
    manifest = tmp_path / "runtime" / "system_tools" / "demo" / "manifest.json"
    user_output = tmp_path / "workspace" / "default" / "threads" / "t1" / "outputs" / "report.docx"
    for path in (old_tmp, old_artifact, manifest, user_output):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("data", encoding="utf-8")
        _age(path, 45)

    preview = cleanup_artifacts(root=tmp_path, dry_run=True)
    assert preview["candidate_count"] == 2
    assert old_tmp.exists() and old_artifact.exists()

    applied = cleanup_artifacts(root=tmp_path, dry_run=False)
    assert applied["removed_count"] == 2
    assert not old_tmp.exists() and not old_artifact.exists()
    assert manifest.exists()
    assert user_output.exists()
