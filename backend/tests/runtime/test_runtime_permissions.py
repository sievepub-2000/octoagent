from pathlib import Path

from src.runtime.config.paths import Paths
from src.runtime.permissions import runtime_write_roots


def test_default_backend_state_is_below_runtime_root(tmp_path: Path) -> None:
    paths = Paths(tmp_path)

    roots = runtime_write_roots(paths)

    assert roots[0] == tmp_path / "runtime" / "backend-state"
    assert all(Path(root).is_relative_to(tmp_path) for root in roots)


def test_explicit_backend_state_root_is_preserved(tmp_path: Path) -> None:
    paths = Paths(tmp_path / "workspace")
    explicit = tmp_path / "external-state"

    roots = runtime_write_roots(paths, explicit)

    assert roots[0] == explicit
