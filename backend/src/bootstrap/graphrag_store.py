"""Project-managed GraphRAG adapter for bootstrap retrieval."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GraphRAGQueryResult:
    method: str
    response: str


class BootstrapGraphRAGStore:
    """Thin adapter around the official microsoft/graphrag CLI."""

    def __init__(self, root_path: Path):
        self._root_path = root_path

    @property
    def root_path(self) -> Path:
        return self._root_path

    @property
    def input_dir(self) -> Path:
        return self._root_path / "input"

    @property
    def output_dir(self) -> Path:
        return self._root_path / "output"

    @property
    def settings_path(self) -> Path:
        return self._root_path / "settings.yaml"

    def cli_available(self) -> bool:
        return importlib.util.find_spec("graphrag") is not None

    def is_initialized(self) -> bool:
        return self.settings_path.exists()

    def has_index(self) -> bool:
        return self.output_dir.exists() and any(self.output_dir.rglob("*.parquet"))

    def ensure_project_initialized(self, force: bool = False) -> bool:
        self._root_path.mkdir(parents=True, exist_ok=True)
        self.input_dir.mkdir(parents=True, exist_ok=True)

        if not self.cli_available():
            return False

        if self.is_initialized() and not force:
            return True

        subprocess.run(
            [
                sys.executable,
                "-m",
                "graphrag",
                "init",
                "-r",
                str(self._root_path),
                "-f",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return self.is_initialized()

    def sync_documents(self, documents: list[tuple[str, str]]) -> int:
        self._root_path.mkdir(parents=True, exist_ok=True)
        self.input_dir.mkdir(parents=True, exist_ok=True)

        desired_files: set[Path] = set()
        for source_name, content in documents:
            target = self.input_dir / f"{_safe_slug(source_name)}.md"
            target.write_text(content, encoding="utf-8")
            desired_files.add(target)

        for existing in self.input_dir.glob("*.md"):
            if existing not in desired_files:
                existing.unlink()

        return len(desired_files)

    def query(
        self,
        *,
        query_text: str,
        method: str = "local",
        response_type: str = "List of 3-7 bullet points",
    ) -> GraphRAGQueryResult | None:
        if not self.cli_available() or not self.has_index():
            return None

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "graphrag",
                "query",
                "-r",
                str(self._root_path),
                "-m",
                method,
                "--response-type",
                response_type,
                query_text,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        response = completed.stdout.strip()
        if not response:
            return None
        return GraphRAGQueryResult(method=method, response=response)


def _safe_slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower())
    normalized = normalized.strip("-._")
    return normalized or "document"