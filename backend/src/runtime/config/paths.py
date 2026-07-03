import contextlib
import json
import os
import re
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
import yaml


# Virtual path prefix seen by agents inside the sandbox
VIRTUAL_PATH_PREFIX = "/mnt/user-data"
DEFAULT_WORKSPACE_DIRNAME = "octoagent-workspace"
SETUP_STATE_ENV_VAR = "OCTO_AGENT_SETUP_STATE_FILE"

_SAFE_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def _load_system_default_model_from_config() -> str | None:
    """Load the system-level default model from config.yaml (single source of truth)."""
    try:
        from src.runtime.config.app_config import resolve_app_config_path
        config_path = resolve_app_config_path()
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}
            system_section = config_data.get("system", {})
            default_model = system_section.get("default_model", "").strip()
            if default_model:
                return default_model
    except Exception:
        pass
    return None




def get_setup_state_file() -> Path:
    """Return the user-scoped setup state file path."""
    if env_path := os.getenv(SETUP_STATE_ENV_VAR):
        return Path(env_path).expanduser().resolve()
    return Path.home() / ".config" / "octoagent" / "setup_state.json"


def load_setup_state() -> dict[str, str]:
    """Read persisted setup state from the user-scoped setup file.
    
    Priority: config.yaml system.default_model > setup_state.json default_model
    """
    # First check config.yaml for system-level default model (single source of truth)
    system_default = _load_system_default_model_from_config()
    
    state_file = get_setup_state_file()
    if not state_file.exists():
        if system_default:
            return {"default_model": system_default}
        return {}
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        if system_default:
            return {"default_model": system_default}
        return {}
    if not isinstance(payload, dict):
        if system_default:
            return {"default_model": system_default}
        return {}
    
    result = {str(key): str(value) for key, value in payload.items() if value is not None}
    
    # Override with config.yaml default_model if present and setup_state doesn't have explicit override
    if system_default and "default_model" not in result:
        result["default_model"] = system_default
    
    return result


def resolve_configured_default_model_name(available_model_names: Iterable[str]) -> str | None:
    """Resolve the effective default model using persisted setup state when possible."""
    model_names = [str(name).strip() for name in available_model_names if str(name).strip()]
    if not model_names:
        return None
    configured_default = load_setup_state().get("default_model", "").strip()
    if configured_default and configured_default in model_names:
        return configured_default
    return model_names[0]


def _load_configured_workspace_root() -> Path | None:
    payload = load_setup_state()
    workspace_path = payload.get("workspace_path") if isinstance(payload, dict) else None
    if not workspace_path:
        return None
    return Path(str(workspace_path)).expanduser().resolve()


def _load_repo_workspace_root() -> Path | None:
    repo_root = Path(__file__).resolve().parents[3]
    workspace_root = repo_root / "workspace"
    if not workspace_root.exists():
        return None
    setup_snapshot = workspace_root / "env" / "setup.json"
    required_dirs = ("default", "env", "workflow", "runtime")
    if setup_snapshot.exists() or all((workspace_root / name).exists() for name in required_dirs):
        return workspace_root.resolve()
    return None


class Paths:
    """Centralized path configuration for OctoAgent runtime and user data."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self._base_dir = Path(base_dir).expanduser().resolve() if base_dir is not None else None

    @property
    def host_base_dir(self) -> Path:
        """Host-visible base dir for Docker volume mount sources."""
        if env := os.getenv("OCTO_AGENT_HOST_BASE_DIR"):
            return Path(env).expanduser().resolve()
        return self.base_dir

    @property
    def base_dir(self) -> Path:
        """Root directory for all non-repo runtime data."""
        if self._base_dir is not None:
            return self._base_dir
        if env_home := os.getenv("OCTO_AGENT_HOME"):
            return Path(env_home).expanduser().resolve()
        if configured_root := _load_configured_workspace_root():
            return configured_root
        if repo_workspace_root := _load_repo_workspace_root():
            return repo_workspace_root
        return (Path.home() / DEFAULT_WORKSPACE_DIRNAME).resolve()

    @property
    def workspace_root(self) -> Path:
        return self.base_dir

    @property
    def default_workspace_dir(self) -> Path:
        return self.base_dir / "default"

    @property
    def code_workspace_dir(self) -> Path:
        return self.default_workspace_dir / "code"

    @property
    def env_dir(self) -> Path:
        return self.base_dir / "env"

    @property
    def workflow_root(self) -> Path:
        return self.base_dir / "workflow"

    @property
    def workflow_tasks_dir(self) -> Path:
        return self.workflow_root / "taskwork"

    @property
    def workflow_tasks_state_dir(self) -> Path:
        return self.workflow_tasks_dir / "_state"

    @property
    def runtime_root(self) -> Path:
        return self.base_dir / "runtime"

    @property
    def memory_file(self) -> Path:
        return self.default_workspace_dir / "memory.json"

    @property
    def user_md_file(self) -> Path:
        return self.default_workspace_dir / "USER.md"

    @property
    def agents_dir(self) -> Path:
        return self.default_workspace_dir / "agents"

    @property
    def channels_store_dir(self) -> Path:
        return self.runtime_root / "channels"

    @property
    def hooks_store_dir(self) -> Path:
        return self.runtime_root / "hooks"

    @property
    def plugin_registry_dir(self) -> Path:
        return self.runtime_root / "plugins"

    @property
    def browser_runtime_dir(self) -> Path:
        return self.runtime_root / "browser_runtime"

    @property
    def system_execution_dir(self) -> Path:
        return self.runtime_root / "system_execution"

    def agent_dir(self, name: str) -> Path:
        return self.agents_dir / name.lower()

    def agent_memory_file(self, name: str) -> Path:
        return self.agent_dir(name) / "memory.json"

    def thread_dir(self, thread_id: str) -> Path:
        if not _SAFE_THREAD_ID_RE.match(thread_id):
            raise ValueError(f"Invalid thread_id {thread_id!r}: only alphanumeric characters, hyphens, and underscores are allowed.")
        return self.default_workspace_dir / "threads" / thread_id

    def code_session_dir(self, thread_id: str) -> Path:
        if not _SAFE_THREAD_ID_RE.match(thread_id):
            raise ValueError(f"Invalid thread_id {thread_id!r}: only alphanumeric characters, hyphens, and underscores are allowed.")
        return self.code_workspace_dir / thread_id

    def sandbox_work_dir(self, thread_id: str) -> Path:
        return self.code_session_dir(thread_id) / "workspace"

    def sandbox_uploads_dir(self, thread_id: str) -> Path:
        return self.thread_dir(thread_id) / "uploads"

    def sandbox_outputs_dir(self, thread_id: str) -> Path:
        return self.thread_dir(thread_id) / "outputs"

    def sandbox_user_data_dir(self, thread_id: str) -> Path:
        return self.thread_dir(thread_id)

    def ensure_thread_dirs(self, thread_id: str) -> None:
        for directory in [
            self.thread_dir(thread_id),
            self.sandbox_work_dir(thread_id),
            self.sandbox_uploads_dir(thread_id),
            self.sandbox_outputs_dir(thread_id),
        ]:
            directory.mkdir(parents=True, exist_ok=True)
            with contextlib.suppress(PermissionError, OSError):
                directory.chmod(0o777)

    def resolve_virtual_path(self, thread_id: str, virtual_path: str) -> Path:
        stripped = virtual_path.lstrip("/")
        prefix = VIRTUAL_PATH_PREFIX.lstrip("/")
        if stripped != prefix and not stripped.startswith(prefix + "/"):
            raise ValueError(f"Path must start with /{prefix}")

        relative = stripped[len(prefix) :].lstrip("/")
        if not relative:
            return self.sandbox_user_data_dir(thread_id)

        relative_path = PurePosixPath(relative)
        head, *tail = relative_path.parts
        mapped_bases = {
            "workspace": self.sandbox_work_dir(thread_id),
            "uploads": self.sandbox_uploads_dir(thread_id),
            "outputs": self.sandbox_outputs_dir(thread_id),
        }
        base = mapped_bases.get(head, self.sandbox_user_data_dir(thread_id))
        suffix = Path(*tail) if head in mapped_bases else Path(relative)
        actual = (base / suffix).resolve()

        allowed_roots = [
            self.sandbox_user_data_dir(thread_id).resolve(),
            self.sandbox_work_dir(thread_id).resolve(),
            self.sandbox_uploads_dir(thread_id).resolve(),
            self.sandbox_outputs_dir(thread_id).resolve(),
        ]
        for root in allowed_roots:
            try:
                actual.relative_to(root)
                return actual
            except ValueError:
                continue
        raise ValueError("Access denied: path traversal detected")


_paths: Paths | None = None


def get_paths() -> Paths:
    global _paths
    if _paths is None:
        _paths = Paths()
    return _paths


def resolve_path(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = get_paths().base_dir / path
    return p.resolve()
