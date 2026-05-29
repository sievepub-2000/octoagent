"""OctoAgentClient — Embedded Python client for OctoAgent agent system.

Provides direct programmatic access to OctoAgent's agent capabilities
without requiring LangGraph Server or Gateway API processes.

Usage:
    from src.interfaces.embedded.client import OctoAgentClient

    client = OctoAgentClient()
    response = client.chat("Analyze this paper for me", thread_id="my-thread")
    print(response)

    # Streaming
    for event in client.stream("hello"):
        print(event)
"""

import asyncio
import json
import logging
import mimetypes
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.resource_profile import get_resource_profile
from src.agents.thread_state import ThreadState
from src.interfaces.embedded.agent import ClientAgentBuilder
from src.interfaces.embedded.streaming import ClientStreamSerializer
from src.models import create_chat_model
from src.runtime.config.app_config import get_app_config, reload_app_config
from src.runtime.config.extensions_config import ExtensionsConfig, McpServerConfig, SkillStateConfig, get_extensions_config, reload_extensions_config
from src.runtime.config.paths import get_paths

logger = logging.getLogger(__name__)


def _as_bool(value: Any, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _as_optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


@dataclass
class StreamEvent:
    """A single event from the streaming agent response.

    Event types align with the LangGraph SSE protocol:
        - ``"values"``: Full state snapshot (title, messages, artifacts).
        - ``"messages-tuple"``: Per-message update (AI text, tool calls, tool results).
        - ``"end"``: Stream finished.

    Attributes:
        type: Event type.
        data: Event payload. Contents vary by type.
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)


class OctoAgentClient:
    """Embedded Python client for OctoAgent agent system.

    Provides direct programmatic access to OctoAgent's agent capabilities
    without requiring LangGraph Server or Gateway API processes.

    Note:
        Multi-turn conversations require a ``checkpointer``. Without one,
        each ``stream()`` / ``chat()`` call is stateless — ``thread_id``
        is only used for file isolation (uploads / artifacts).

        The system prompt (including date, memory, and skills context) is
        generated when the internal agent is first created and cached until
        the configuration key changes. Call :meth:`reset_agent` to force
        a refresh in long-running processes.

    Example::

        from src.interfaces.embedded.client import OctoAgentClient

        client = OctoAgentClient()

        # Simple one-shot
        print(client.chat("hello"))

        # Streaming
        for event in client.stream("hello"):
            print(event.type, event.data)

        # Configuration queries
        print(client.list_models())
        print(client.list_skills())
    """

    def __init__(
        self,
        config_path: str | None = None,
        checkpointer=None,
        *,
        model_name: str | None = None,
        thinking_enabled: bool = False,
        subagent_enabled: bool = False,
        plan_mode: bool = False,
        agent_runtime_provider: str | None = None,
    ):
        """Initialize the client.

        Loads configuration but defers agent creation to first use.

        Args:
            config_path: Path to config.yaml. Uses default resolution if None.
            checkpointer: LangGraph checkpointer instance for state persistence.
                Required for multi-turn conversations on the same thread_id.
                Without a checkpointer, each call is stateless.
            model_name: Override the default model name from config.
            thinking_enabled: Enable model's extended thinking.
            subagent_enabled: Enable subagent delegation.
            plan_mode: Enable TodoList middleware for plan mode.
            agent_runtime_provider: Runtime provider name. Legacy values are
                normalized to the LangGraph path; LangGraph is the only active
                runtime provider.
        """
        if config_path is not None:
            reload_app_config(config_path)
        self._app_config = get_app_config()

        self._checkpointer = checkpointer
        self._model_name = model_name
        self._thinking_enabled = thinking_enabled
        self._subagent_enabled = subagent_enabled
        self._plan_mode = plan_mode
        self._agent_runtime_provider = None if agent_runtime_provider in {None, "", "langgraph"} else "langgraph"

        # Lazy agent — created on first call, recreated when config changes.
        self._agent = None
        self._agent_config_key: tuple | None = None

    def reset_agent(self) -> None:
        """Force the internal agent to be recreated on the next call.

        Use this after external changes (e.g. memory updates, skill
        installations) that should be reflected in the system prompt
        or tool set.
        """
        self._agent = None
        self._agent_config_key = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _atomic_write_json(path: Path, data: dict) -> None:
        """Write JSON to *path* atomically (temp file + replace)."""
        fd = tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        )
        try:
            json.dump(data, fd, indent=2)
            fd.close()
            Path(fd.name).replace(path)
        except BaseException:
            fd.close()
            Path(fd.name).unlink(missing_ok=True)
            raise

    def _get_runnable_config(self, thread_id: str, **overrides) -> RunnableConfig:
        """Build a RunnableConfig for agent invocation."""
        configurable = {
            "thread_id": thread_id,
            "model_name": overrides.get("model_name", self._model_name),
            "thinking_enabled": overrides.get("thinking_enabled", self._thinking_enabled),
            "is_plan_mode": overrides.get("plan_mode", self._plan_mode),
            "subagent_enabled": overrides.get("subagent_enabled", self._subagent_enabled),
        }
        return RunnableConfig(
            configurable=configurable,
            recursion_limit=overrides.get("recursion_limit", get_resource_profile().recursion_default),
        )

    def _ensure_agent(self, config: RunnableConfig):
        """Create (or recreate) the agent when config-dependent params change."""
        cfg = config.get("configurable", {})
        key = (
            cfg.get("model_name"),
            cfg.get("thinking_enabled"),
            cfg.get("is_plan_mode"),
            cfg.get("subagent_enabled"),
        )

        if self._agent is not None and self._agent_config_key == key:
            return

        self._agent = self._make_agent_builder().build(config, checkpointer=self._checkpointer)
        self._agent_config_key = key

    @staticmethod
    def _load_default_checkpointer():
        from src.agents.checkpointer import get_checkpointer

        return get_checkpointer()

    def _make_agent_builder(self) -> ClientAgentBuilder:
        # Lazy imports — only needed for the LangGraph execution path
        from src.agents.lead_agent.agent import _build_middlewares
        from src.agents.lead_agent.prompt import apply_prompt_template

        return ClientAgentBuilder(
            create_chat_model_fn=create_chat_model,
            get_tools_fn=self._get_tools,
            build_middlewares_fn=_build_middlewares,
            apply_prompt_template_fn=apply_prompt_template,
            create_agent_fn=create_agent,
            get_checkpointer_fn=self._load_default_checkpointer,
            thread_state_cls=ThreadState,
        )

    @staticmethod
    def _get_tools(*, model_name: str | None, subagent_enabled: bool):
        """Lazy import to avoid circular dependency at module level."""
        from src.tools import get_available_tools

        return get_available_tools(model_name=model_name, subagent_enabled=subagent_enabled)

    _serialize_message = staticmethod(ClientStreamSerializer.serialize_message)

    _extract_text = staticmethod(ClientStreamSerializer.extract_text)

    @staticmethod
    def _has_meaningful_message_event(events: list[StreamEvent]) -> bool:
        for event in events:
            if event.type != "messages-tuple":
                continue
            if event.data.get("type") == "tool":
                return True
            if event.data.get("tool_calls"):
                return True
            if event.data.get("type") == "ai" and event.data.get("content"):
                return True
        return False

    @staticmethod
    def _saw_runtime_message(events: list[StreamEvent]) -> bool:
        for event in events:
            if event.type != "values":
                continue
            for message in event.data.get("messages", []):
                if message.get("type") in {"ai", "tool"}:
                    return True
        return False

    def _stream_once(
        self,
        message: str,
        *,
        thread_id: str,
        **kwargs,
    ) -> list[StreamEvent]:
        config = self._get_runnable_config(thread_id, **kwargs)
        self._ensure_agent(config)

        state: dict[str, Any] = {"messages": [HumanMessage(content=message)]}
        events: list[StreamEvent] = []
        emitted_ai_text: dict[str, str] = {}
        emitted_ai_tool_calls: set[str] = set()
        emitted_tool_messages: set[str] = set()

        context = {"thread_id": thread_id}

        for chunk in self._agent.stream(state, config=config, context=context, stream_mode="values"):
            chunk_with_state = dict(chunk)
            chunk_with_state["_emitted_ai_text"] = emitted_ai_text
            chunk_with_state["_emitted_ai_tool_calls"] = emitted_ai_tool_calls
            chunk_with_state["_emitted_tool_messages"] = emitted_tool_messages
            events.extend(ClientStreamSerializer.normalize_chunk_events(chunk_with_state, StreamEvent))

        events.append(StreamEvent(type="end", data={}))
        return events

    @staticmethod
    def _looks_like_tool_or_side_effect_request(message: str) -> bool:
        lowered = message.lower()
        markers = [
            "use the ",
            "tool",
            "write_file",
            "read_file",
            "bash",
            "ls ",
            "browser",
            "shell",
            "command",
            "file",
            "/mnt/user-data/",
        ]
        return any(marker in lowered for marker in markers)

    def _direct_chat_fallback_events(
        self,
        message: str,
        *,
        thread_id: str,
        **kwargs,
    ) -> list[StreamEvent]:
        config = self._get_runnable_config(thread_id, **kwargs)
        cfg = config.get("configurable", {})
        reply = create_chat_model(
            name=cfg.get("model_name"),
            thinking_enabled=cfg.get("thinking_enabled", self._thinking_enabled),
        ).invoke([HumanMessage(content=message)])
        return ClientStreamSerializer.fallback_events(message=message, reply=reply, stream_event_cls=StreamEvent)

    # ------------------------------------------------------------------
    # Public API — conversation
    # ------------------------------------------------------------------

    def stream(
        self,
        message: str,
        *,
        thread_id: str | None = None,
        **kwargs,
    ) -> Generator[StreamEvent, None, None]:
        """Stream a conversation turn, yielding events incrementally.

        Each call sends one user message and yields events until the agent
        finishes its turn. A ``checkpointer`` must be provided at init time
        for multi-turn context to be preserved across calls.

        Event types align with the LangGraph SSE protocol so that
        consumers can switch between HTTP streaming and embedded mode
        without changing their event-handling logic.

        Args:
            message: User message text.
            thread_id: Thread ID for conversation context. Auto-generated if None.
            **kwargs: Override client defaults (model_name, thinking_enabled,
                plan_mode, subagent_enabled, recursion_limit).

        Yields:
            StreamEvent with one of:
            - type="values"          data={"title": str|None, "messages": [...], "artifacts": [...]}
            - type="messages-tuple"  data={"type": "ai", "content": str, "id": str}
            - type="messages-tuple"  data={"type": "ai", "content": "", "id": str, "tool_calls": [...]}
            - type="messages-tuple"  data={"type": "tool", "content": str, "name": str, "tool_call_id": str, "id": str}
            - type="end"             data={}
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())
        max_attempts = 3 if self._checkpointer is None else 1
        last_events: list[StreamEvent] = []
        for attempt in range(max_attempts):
            try:
                events = self._stream_once(message, thread_id=thread_id, **kwargs)
                last_events = events
                needs_retry = self._saw_runtime_message(events) and not self._has_meaningful_message_event(events)
                if not needs_retry:
                    for event in events:
                        yield event
                    return
                if attempt == max_attempts - 1:
                    break
                logger.warning(
                    "Retrying client stream because the attempt produced no message events (thread_id=%s, attempt=%s).",
                    thread_id,
                    attempt + 1,
                )
            except Exception:
                if attempt == max_attempts - 1:
                    raise
                logger.warning(
                    "Retrying client stream after transient execution failure (thread_id=%s, attempt=%s).",
                    thread_id,
                    attempt + 1,
                    exc_info=True,
                )
        if not self._looks_like_tool_or_side_effect_request(message):
            try:
                fallback_events = self._direct_chat_fallback_events(
                    message,
                    thread_id=thread_id,
                    **kwargs,
                )
                for event in fallback_events:
                    yield event
                return
            except Exception:
                logger.warning(
                    "Direct chat fallback failed after empty agent responses (thread_id=%s).",
                    thread_id,
                    exc_info=True,
                )
        for event in last_events:
            yield event

    def chat(self, message: str, *, thread_id: str | None = None, **kwargs) -> str:
        """Send a message and return the final text response.

        Convenience wrapper around :meth:`stream` that returns only the
        **last** AI text from ``messages-tuple`` events. If the agent emits
        multiple text segments in one turn, intermediate segments are
        discarded. Use :meth:`stream` directly to capture all events.

        Args:
            message: User message text.
            thread_id: Thread ID for conversation context. Auto-generated if None.
            **kwargs: Override client defaults (same as stream()).

        Returns:
            The last AI message text, or empty string if no response.
        """
        last_text = ""
        for event in self.stream(message, thread_id=thread_id, **kwargs):
            if event.type == "messages-tuple" and event.data.get("type") == "ai":
                content = event.data.get("content", "")
                if content:
                    last_text = content
        return last_text

    # ------------------------------------------------------------------
    # Public API — configuration queries
    # ------------------------------------------------------------------

    def list_models(self) -> dict:
        """List available models from configuration.

        Returns:
            Dict with "models" key containing list of model info dicts,
            matching the Gateway API ``ModelsListResponse`` schema.
        """
        return {
            "models": [
                {
                    "name": model.name,
                    "display_name": getattr(model, "display_name", None),
                    "description": getattr(model, "description", None),
                    "supports_thinking": _as_bool(getattr(model, "supports_thinking", False)),
                    "supports_reasoning_effort": _as_bool(getattr(model, "supports_reasoning_effort", False)),
                    "supports_vision": _as_bool(getattr(model, "supports_vision", False)),
                    "fallback_models": _as_str_list(getattr(model, "fallback_models", [])),
                    "max_context_tokens": _as_optional_int(getattr(model, "max_context_tokens", None)),
                    "is_embedded_backup": False,
                }
                for model in self._app_config.models
            ]
        }

    def list_skills(self, enabled_only: bool = False) -> dict:
        """List available skills.

        Args:
            enabled_only: If True, only return enabled skills.

        Returns:
            Dict with "skills" key containing list of skill info dicts,
            matching the Gateway API ``SkillsListResponse`` schema.
        """
        from src.storage.skills.loader import load_skills

        return {
            "skills": [
                {
                    "name": s.name,
                    "description": s.description,
                    "license": s.license,
                    "category": s.category,
                    "enabled": s.enabled,
                }
                for s in load_skills(enabled_only=enabled_only)
            ]
        }

    def get_memory(self) -> dict:
        """Get current memory data.

        Returns:
            Memory data dict (see src/agents/memory/updater.py for structure).
        """
        from src.agents.memory.updater import get_memory_data

        return get_memory_data()

    def get_model(self, name: str) -> dict | None:
        """Get a specific model's configuration by name.

        Args:
            name: Model name.

        Returns:
            Model info dict matching the Gateway API ``ModelResponse``
            schema, or None if not found.
        """
        model = self._app_config.get_model_config(name)
        if model is None:
            return None
        return {
            "name": model.name,
            "display_name": getattr(model, "display_name", None),
            "description": getattr(model, "description", None),
            "supports_thinking": _as_bool(getattr(model, "supports_thinking", False)),
            "supports_reasoning_effort": _as_bool(getattr(model, "supports_reasoning_effort", False)),
            "supports_vision": _as_bool(getattr(model, "supports_vision", False)),
            "fallback_models": _as_str_list(getattr(model, "fallback_models", [])),
            "max_context_tokens": _as_optional_int(getattr(model, "max_context_tokens", None)),
            "is_embedded_backup": False,
        }

    # ------------------------------------------------------------------
    # Public API — MCP configuration
    # ------------------------------------------------------------------

    def get_mcp_config(self) -> dict:
        """Get MCP server configurations.

        Returns:
            Dict with "mcp_servers" key mapping server name to config,
            matching the Gateway API ``McpConfigResponse`` schema.
        """
        config = get_extensions_config()
        return {"mcp_servers": {name: server.model_dump() for name, server in config.mcp_servers.items()}}

    def update_mcp_config(self, mcp_servers: dict[str, dict]) -> dict:
        """Update MCP server configurations.

        Writes to extensions_config.json and reloads the cache.

        Args:
            mcp_servers: Dict mapping server name to config dict.
                Each value should contain keys like enabled, type, command, args, env, url, etc.

        Returns:
            Dict with "mcp_servers" key, matching the Gateway API
            ``McpConfigResponse`` schema.

        Raises:
            OSError: If the config file cannot be written.
        """
        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            raise FileNotFoundError("Cannot locate extensions_config.json. Set OCTO_AGENT_EXTENSIONS_CONFIG_PATH or ensure it exists in the project root.")

        current_config = get_extensions_config()

        current_config.mcp_servers = {name: McpServerConfig.model_validate(server) for name, server in mcp_servers.items()}

        config_data = current_config.to_serializable_dict()

        self._atomic_write_json(config_path, config_data)

        self._agent = None
        reloaded = reload_extensions_config()
        return {"mcp_servers": {name: server.model_dump() for name, server in reloaded.mcp_servers.items()}}

    # ------------------------------------------------------------------
    # Public API — skills management
    # ------------------------------------------------------------------

    def get_skill(self, name: str) -> dict | None:
        """Get a specific skill by name.

        Args:
            name: Skill name.

        Returns:
            Skill info dict, or None if not found.
        """
        from src.storage.skills.loader import load_skills

        skill = next((s for s in load_skills(enabled_only=False) if s.name == name), None)
        if skill is None:
            return None
        return {
            "name": skill.name,
            "description": skill.description,
            "license": skill.license,
            "category": skill.category,
            "enabled": skill.enabled,
        }

    def update_skill(self, name: str, *, enabled: bool) -> dict:
        """Update a skill's enabled status.

        Args:
            name: Skill name.
            enabled: New enabled status.

        Returns:
            Updated skill info dict.

        Raises:
            ValueError: If the skill is not found.
            OSError: If the config file cannot be written.
        """
        from src.storage.skills.loader import load_skills

        skills = load_skills(enabled_only=False)
        skill = next((s for s in skills if s.name == name), None)
        if skill is None:
            raise ValueError(f"Skill '{name}' not found")

        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            raise FileNotFoundError("Cannot locate extensions_config.json. Set OCTO_AGENT_EXTENSIONS_CONFIG_PATH or ensure it exists in the project root.")

        extensions_config = get_extensions_config()
        extensions_config.skills[name] = SkillStateConfig(enabled=enabled)

        config_data = extensions_config.to_serializable_dict()

        self._atomic_write_json(config_path, config_data)

        self._agent = None
        reload_extensions_config()

        updated = next((s for s in load_skills(enabled_only=False) if s.name == name), None)
        if updated is None:
            raise RuntimeError(f"Skill '{name}' disappeared after update")
        return {
            "name": updated.name,
            "description": updated.description,
            "license": updated.license,
            "category": updated.category,
            "enabled": updated.enabled,
        }

    def install_skill(self, skill_path: str | Path) -> dict:
        """Install a skill from a .skill archive (ZIP).

        Args:
            skill_path: Path to the .skill file.

        Returns:
            Dict with success, skill_name, message.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is invalid.
        """
        from src.gateway.routers.skills import _validate_skill_frontmatter
        from src.storage.skills.loader import get_skills_root_path

        path = Path(skill_path)
        if not path.exists():
            raise FileNotFoundError(f"Skill file not found: {skill_path}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {skill_path}")
        if path.suffix != ".skill":
            raise ValueError("File must have .skill extension")
        if not zipfile.is_zipfile(path):
            raise ValueError("File is not a valid ZIP archive")

        skills_root = get_skills_root_path()
        custom_dir = skills_root / "custom"
        custom_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with zipfile.ZipFile(path, "r") as zf:
                total_size = sum(info.file_size for info in zf.infolist())
                if total_size > 100 * 1024 * 1024:
                    raise ValueError("Skill archive too large when extracted (>100MB)")
                for info in zf.infolist():
                    if Path(info.filename).is_absolute() or ".." in Path(info.filename).parts:
                        raise ValueError(f"Unsafe path in archive: {info.filename}")
                zf.extractall(tmp_path)
            for p in tmp_path.rglob("*"):
                if p.is_symlink():
                    p.unlink()

            items = list(tmp_path.iterdir())
            if not items:
                raise ValueError("Skill archive is empty")

            skill_dir = items[0] if len(items) == 1 and items[0].is_dir() else tmp_path

            is_valid, message, skill_name = _validate_skill_frontmatter(skill_dir)
            if not is_valid:
                raise ValueError(f"Invalid skill: {message}")
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", skill_name):
                raise ValueError(f"Invalid skill name: {skill_name}")

            target = custom_dir / skill_name
            if target.exists():
                raise ValueError(f"Skill '{skill_name}' already exists")

            shutil.copytree(skill_dir, target)

        return {"success": True, "skill_name": skill_name, "message": f"Skill '{skill_name}' installed successfully"}

    # ------------------------------------------------------------------
    # Public API — memory management
    # ------------------------------------------------------------------

    def reload_memory(self) -> dict:
        """Reload memory data from file, forcing cache invalidation.

        Returns:
            The reloaded memory data dict.
        """
        from src.agents.memory.updater import reload_memory_data

        return reload_memory_data()

    def get_memory_config(self) -> dict:
        """Get memory system configuration.

        Returns:
            Memory config dict.
        """
        from src.runtime.config.memory_config import get_memory_config

        config = get_memory_config()
        return {
            "enabled": config.enabled,
            "storage_path": config.storage_path,
            "debounce_seconds": config.debounce_seconds,
            "max_facts": config.max_facts,
            "fact_confidence_threshold": config.fact_confidence_threshold,
            "injection_enabled": config.injection_enabled,
            "max_injection_tokens": config.max_injection_tokens,
        }

    def get_memory_status(self) -> dict:
        """Get memory status: config + current data.

        Returns:
            Dict with "config" and "data" keys.
        """
        return {
            "config": self.get_memory_config(),
            "data": self.get_memory(),
        }

    # ------------------------------------------------------------------
    # Public API — file uploads
    # ------------------------------------------------------------------

    @staticmethod
    def _get_uploads_dir(thread_id: str) -> Path:
        """Get (and create) the uploads directory for a thread."""
        base = get_paths().sandbox_uploads_dir(thread_id)
        base.mkdir(parents=True, exist_ok=True)
        return base

    def upload_files(self, thread_id: str, files: list[str | Path]) -> dict:
        """Upload local files into a thread's uploads directory.

        For PDF, PPT, Excel, and Word files, they are also converted to Markdown.

        Args:
            thread_id: Target thread ID.
            files: List of local file paths to upload.

        Returns:
            Dict with success, files, message — matching the Gateway API
            ``UploadResponse`` schema.

        Raises:
            FileNotFoundError: If any file does not exist.
            ValueError: If any supplied path exists but is not a regular file.
        """
        from src.gateway.routers.uploads import CONVERTIBLE_EXTENSIONS, convert_file_to_markdown

        # Validate all files upfront to avoid partial uploads.
        resolved_files = []
        convertible_extensions = {ext.lower() for ext in CONVERTIBLE_EXTENSIONS}
        has_convertible_file = False
        for f in files:
            p = Path(f)
            if not p.exists():
                raise FileNotFoundError(f"File not found: {f}")
            if not p.is_file():
                raise ValueError(f"Path is not a file: {f}")
            resolved_files.append(p)
            if not has_convertible_file and p.suffix.lower() in convertible_extensions:
                has_convertible_file = True

        uploads_dir = self._get_uploads_dir(thread_id)
        uploaded_files: list[dict] = []

        conversion_pool = None
        if has_convertible_file:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                conversion_pool = None
            else:
                import concurrent.futures

                # Reuse one worker when already inside an event loop to avoid
                # creating a new ThreadPoolExecutor per converted file.
                conversion_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        def _convert_in_thread(path: Path):
            return asyncio.run(convert_file_to_markdown(path))

        try:
            for src_path in resolved_files:
                dest = uploads_dir / src_path.name
                shutil.copy2(src_path, dest)

                info: dict[str, Any] = {
                    "filename": src_path.name,
                    "size": str(dest.stat().st_size),
                    "path": str(dest),
                    "virtual_path": f"/mnt/user-data/uploads/{src_path.name}",
                    "artifact_url": f"/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/{src_path.name}",
                }

                if src_path.suffix.lower() in convertible_extensions:
                    try:
                        if conversion_pool is not None:
                            md_path = conversion_pool.submit(_convert_in_thread, dest).result()
                        else:
                            md_path = asyncio.run(convert_file_to_markdown(dest))
                    except Exception:
                        logger.warning(
                            "Failed to convert %s to markdown",
                            src_path.name,
                            exc_info=True,
                        )
                        md_path = None

                    if md_path is not None:
                        info["markdown_file"] = md_path.name
                        info["markdown_virtual_path"] = f"/mnt/user-data/uploads/{md_path.name}"
                        info["markdown_artifact_url"] = f"/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/{md_path.name}"

                uploaded_files.append(info)
        finally:
            if conversion_pool is not None:
                conversion_pool.shutdown(wait=True)

        return {
            "success": True,
            "files": uploaded_files,
            "message": f"Successfully uploaded {len(uploaded_files)} file(s)",
        }

    def list_uploads(self, thread_id: str) -> dict:
        """List files in a thread's uploads directory.

        Args:
            thread_id: Thread ID.

        Returns:
            Dict with "files" and "count" keys, matching the Gateway API
            ``list_uploaded_files`` response.
        """
        uploads_dir = self._get_uploads_dir(thread_id)
        if not uploads_dir.exists():
            return {"files": [], "count": 0}

        files = []
        with os.scandir(uploads_dir) as entries:
            file_entries = [entry for entry in entries if entry.is_file()]

        for entry in sorted(file_entries, key=lambda item: item.name):
            stat = entry.stat()
            filename = entry.name
            files.append(
                {
                    "filename": filename,
                    "size": str(stat.st_size),
                    "path": str(Path(entry.path)),
                    "virtual_path": f"/mnt/user-data/uploads/{filename}",
                    "artifact_url": f"/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/{filename}",
                    "extension": Path(filename).suffix,
                    "modified": stat.st_mtime,
                }
            )
        return {"files": files, "count": len(files)}

    def delete_upload(self, thread_id: str, filename: str) -> dict:
        """Delete a file from a thread's uploads directory.

        Args:
            thread_id: Thread ID.
            filename: Filename to delete.

        Returns:
            Dict with success and message, matching the Gateway API
            ``delete_uploaded_file`` response.

        Raises:
            FileNotFoundError: If the file does not exist.
            PermissionError: If path traversal is detected.
        """
        uploads_dir = self._get_uploads_dir(thread_id)
        file_path = (uploads_dir / filename).resolve()

        try:
            file_path.relative_to(uploads_dir.resolve())
        except ValueError as exc:
            raise PermissionError("Access denied: path traversal detected") from exc

        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {filename}")

        file_path.unlink()
        return {"success": True, "message": f"Deleted {filename}"}

    # ------------------------------------------------------------------
    # Public API — artifacts
    # ------------------------------------------------------------------

    def get_artifact(self, thread_id: str, path: str) -> tuple[bytes, str]:
        """Read an artifact file produced by the agent.

        Args:
            thread_id: Thread ID.
            path: Virtual path (e.g. "mnt/user-data/outputs/file.txt").

        Returns:
            Tuple of (file_bytes, mime_type).

        Raises:
            FileNotFoundError: If the artifact does not exist.
            ValueError: If the path is invalid.
        """
        virtual_prefix = "mnt/user-data"
        clean_path = path.lstrip("/")
        if not clean_path.startswith(virtual_prefix):
            raise ValueError(f"Path must start with /{virtual_prefix}")

        paths = get_paths()
        actual = None
        resolver = getattr(paths, "resolve_virtual_path", None)
        if callable(resolver):
            candidate = resolver(thread_id, clean_path)
            if isinstance(candidate, Path):
                actual = candidate
        if actual is None:
            relative = clean_path[len(virtual_prefix) :].lstrip("/")
            base_dir = paths.sandbox_user_data_dir(thread_id)
            actual = (base_dir / relative).resolve()

            try:
                actual.relative_to(base_dir.resolve())
            except ValueError as exc:
                raise PermissionError("Access denied: path traversal detected") from exc
        if not actual.exists():
            raise FileNotFoundError(f"Artifact not found: {path}")
        if not actual.is_file():
            raise ValueError(f"Path is not a file: {path}")

        mime_type, _ = mimetypes.guess_type(actual)
        return actual.read_bytes(), mime_type or "application/octet-stream"
