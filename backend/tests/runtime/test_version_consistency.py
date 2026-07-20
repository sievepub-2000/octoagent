from __future__ import annotations

import json
import re
from pathlib import Path


def test_release_version_is_consistent_across_runtime_surfaces() -> None:
    # This file is installed under backend/tests/runtime/ in the repository.
    repo = Path(__file__).resolve().parents[3]
    backend_text = (repo / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    app_text = (repo / "backend" / "src" / "gateway" / "app.py").read_text(encoding="utf-8")
    persona_text = (repo / "runtime" / "config" / "persona.md").read_text(encoding="utf-8")
    frontend = json.loads((repo / "frontend" / "package.json").read_text(encoding="utf-8"))

    backend_version = re.search(r'^version\s*=\s*"([^"]+)"', backend_text, re.MULTILINE)
    gateway_version = re.search(r'version="([^"]+)"', app_text)
    persona_version = re.search(r'^- \*\*Version\*\*: ([^\s]+)', persona_text, re.MULTILINE)
    assert backend_version and gateway_version and persona_version
    versions = {backend_version.group(1), gateway_version.group(1), persona_version.group(1), str(frontend["version"])}
    assert versions == {"20260720"}


if __name__ == "__main__":
    test_release_version_is_consistent_across_runtime_surfaces()
    print("version-consistency-ok")
