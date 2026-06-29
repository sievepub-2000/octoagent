from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from src.utils.serialization import fmt_json as _json

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ARTIFACT_ROOT = _REPO_ROOT / "runtime" / "system_tools"
_WRITING_ROOT = _ARTIFACT_ROOT / "writing-suite"
_WRITING_PYTHON = _ARTIFACT_ROOT / "writing-python" / ".venv" / "bin" / "python"
_RUNTIME_TOOLS = _REPO_ROOT / "runtime" / "tools"
_RUNTIME_BIN = _RUNTIME_TOOLS / "bin"
_TEXTLINT = _RUNTIME_TOOLS / "writing-node" / "node_modules" / ".bin" / "textlint"
_TEXTLINT_CONFIG = _RUNTIME_TOOLS / "writing-node" / ".textlintrc.json"
_FRONTEND_NODE_MODULES = _REPO_ROOT / "frontend" / "node_modules"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


