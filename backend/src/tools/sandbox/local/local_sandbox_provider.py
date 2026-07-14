from src.tools.sandbox.local.local_sandbox import LocalSandbox
from src.tools.sandbox.sandbox import Sandbox
from src.tools.sandbox.sandbox_provider import SandboxProvider

_singleton: LocalSandbox | None = None


class LocalSandboxProvider(SandboxProvider):
    def __init__(self):
        """Initialize the local sandbox provider with path mappings."""
        self._path_mappings = self._setup_path_mappings()

    def _setup_path_mappings(self) -> dict[str, str]:
        """
        Setup path mappings for local sandbox.

        Maps container paths to actual local paths, including skills directory.

        Returns:
            Dictionary of path mappings
        """
        mappings = {}

        # Map skills container path to local skills directory
        try:
            from src.runtime.config import get_app_config

            config = get_app_config()
            skills_path = config.skills.get_skills_path()
            container_path = config.skills.container_path

            # Only add mapping if skills directory exists
            if skills_path.exists():
                mappings[container_path] = str(skills_path)
        except Exception as e:
            # Log but don't fail if config loading fails
            print(f"Warning: Could not setup skills path mapping: {e}")

        return mappings

    def acquire(self, thread_id: str | None = None) -> str:
        global _singleton
        if _singleton is None:
            _singleton = LocalSandbox("local", path_mappings=self._path_mappings)
        return _singleton.id

    def get(self, sandbox_id: str) -> Sandbox | None:
        if sandbox_id == "local":
            if _singleton is None:
                self.acquire()
            return _singleton
        return None

    def release(self, sandbox_id: str) -> None:
        # For local sandbox, cleanup thread-specific directories.
        # The singleton sandbox itself is kept alive for reuse, but we
        # remove stale temp directories tied to completed threads.
        try:
            from src.runtime.config.paths import get_paths

            paths = get_paths()
            base = paths.base_dir
            if base and base.exists():
                import os
                import time

                now = time.time()
                for entry in os.scandir(str(base)):
                    if not entry.is_dir():
                        continue
                    name = entry.name
                    # Clean up directories older than 1 hour
                    # that look like thread data dirs
                    if name.startswith(("thread_", "sandbox_", "ws_")):
                        age = now - entry.stat().st_mtime
                        if age > 3600:
                            import shutil

                            shutil.rmtree(entry.path, ignore_errors=True)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("LocalSandboxProvider.release cleanup error: %s", exc)
