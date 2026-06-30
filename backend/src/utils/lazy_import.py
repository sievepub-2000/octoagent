"""Lazy import helper for optional/heavy dependencies.

Wraps imports that should only execute when the attribute is accessed,
reducing startup time and memory usage for rarely-used backends like
sentence-transformers, faster-whisper, tavily, and faiss.
"""

from __future__ import annotations


class LazyImport:
    """Wraps an import that only executes when the attribute is accessed."""

    def __init__(self, module_path: str, attr_name: str | None = None) -> None:
        self._module_path = module_path
        self._attr_name = attr_name
        self._loaded = False
        self._module = None

    def _load(self) -> None:
        if not self._loaded:
            import importlib
            try:
                self._module = importlib.import_module(self._module_path)
            except ImportError as exc:
                self._module = None
                object.__setattr__(self, '_import_error', exc)
            self._loaded = True

    def __getattr__(self, name: str) -> object:
        self._load()
        if self._module is None:
            raise RuntimeError(
                f"LazyImport '{self._module_path}' failed to load: "
                f"'{getattr(self, '_import_error', 'unknown error')}'"
            )
        if self._attr_name and name == "__wrapped__":
            return self._module
        if self._attr_name:
            return getattr(self._module, self._attr_name)
        return getattr(self._module, name)

    def __bool__(self) -> bool:
        return True

    @property
    def available(self) -> bool:
        """Check whether the underlying module is importable."""
        try:
            self._load()
            return self._module is not None
        except Exception:
            return False


# Pre-defined lazy imports for heavy dependencies
lazy_sentence_transformers = LazyImport("sentence_transformers")
lazy_faiss = LazyImport("faiss", "index_factory")
lazy_tavily = LazyImport("tavily")
lazy_whisper = LazyImport("faster_whisper")

__all__ = [
    "LazyImport",
    "lazy_sentence_transformers",
    "lazy_faiss",
    "lazy_tavily",
    "lazy_whisper",
]
