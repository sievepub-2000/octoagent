"""HookCore service for runtime hook registration, dispatch, and event wiring."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.runtime.config.extensions_config import ExtensionsConfig, HookStateConfig, get_extensions_config, reload_extensions_config
from src.storage.skills.loader import get_skills_root_path

logger = logging.getLogger(__name__)

# Type alias for hook listeners: sync or async callables receiving event payload dict
HookListener = Callable[[dict[str, Any]], Any | Awaitable[Any]]


@dataclass(slots=True)
class RuntimeHookBinding:
    hook_id: str
    event: str
    enabled: bool = True
    source: str = "runtime"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class WebhookRegistration:
    """Tracks a registered webhook endpoint."""

    webhook_id: str
    url: str
    events: list[str]
    enabled: bool = True
    secret: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


# Well-known lifecycle events (callers may use arbitrary strings too)
EVENT_AGENT_STATUS_CHANGED = "agent.status_changed"
EVENT_HANDOFF_CREATED = "agent.handoff_created"
EVENT_TASK_COMPLETED = "task.completed"
EVENT_TASK_FAILED = "task.failed"
EVENT_AGENTS_TERMINATED = "agents.terminated"
EVENT_AGENT_UPDATED = "agent.updated"
EVENT_WORKSPACE_CREATED = "workspace.created"
EVENT_WORKSPACE_UPDATED = "workspace.updated"
EVENT_EXECUTION_STARTED = "execution.started"
EVENT_EXECUTION_COMPLETED = "execution.completed"
EVENT_CAPABILITY_REFRESH = "capability.refresh"
EVENT_CHANNEL_MESSAGE = "channel.message"


class HookCoreService:
    """Stable boundary for runtime hook registration, listener dispatch, and event wiring."""

    _WEBHOOKS_FILE = "webhooks.json"

    def __init__(self, store_dir: Path | None = None) -> None:
        self._bindings: dict[str, RuntimeHookBinding] = {}
        self._listeners: dict[str, list[HookListener]] = defaultdict(list)
        self._webhooks: dict[str, WebhookRegistration] = {}
        self._store_dir = store_dir
        if store_dir is not None:
            self._load_webhooks()

    # ------------------------------------------------------------------
    # Hook binding CRUD
    # ------------------------------------------------------------------

    def list_runtime_hooks(self) -> list[RuntimeHookBinding]:
        return sorted(self._bindings.values(), key=lambda item: item.hook_id)

    def register_runtime_hook(
        self,
        hook_id: str,
        *,
        event: str,
        enabled: bool = True,
        source: str = "runtime",
        metadata: dict[str, object] | None = None,
    ) -> RuntimeHookBinding:
        binding = RuntimeHookBinding(
            hook_id=hook_id,
            event=event,
            enabled=enabled,
            source=source,
            metadata=dict(metadata or {}),
        )
        self._bindings[hook_id] = binding
        return binding

    def remove_runtime_hook(self, hook_id: str) -> bool:
        return self._bindings.pop(hook_id, None) is not None

    # ------------------------------------------------------------------
    # Listener management
    # ------------------------------------------------------------------

    def on(self, event: str, listener: HookListener) -> None:
        """Register a listener callback for a specific event."""
        self._listeners[event].append(listener)

    def off(self, event: str, listener: HookListener) -> None:
        """Remove a previously registered listener."""
        try:
            self._listeners[event].remove(listener)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Webhook management
    # ------------------------------------------------------------------

    _ALLOWED_WEBHOOK_SCHEMES = {"http", "https"}

    def register_webhook(
        self,
        webhook_id: str,
        *,
        url: str,
        events: list[str],
        enabled: bool = True,
        secret: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> WebhookRegistration:
        """Register an external webhook URL to receive event payloads via HTTP POST.

        Only ``http`` and ``https`` schemes are accepted.  Each event in
        *events* gets a listener that posts the payload as JSON.
        """
        parsed = urlparse(url)
        if parsed.scheme not in self._ALLOWED_WEBHOOK_SCHEMES:
            raise ValueError(f"Webhook URL scheme must be one of {self._ALLOWED_WEBHOOK_SCHEMES}, got {parsed.scheme!r}")
        if not parsed.hostname:
            raise ValueError("Webhook URL must include a hostname")

        registration = WebhookRegistration(
            webhook_id=webhook_id,
            url=url,
            events=list(events),
            enabled=enabled,
            secret=secret,
            metadata=dict(metadata or {}),
        )
        self._webhooks[webhook_id] = registration

        # Wire listeners for all subscribed events
        for event in events:
            self.on(event, self._make_webhook_poster(registration))

        self._save_webhooks()
        return registration

    def remove_webhook(self, webhook_id: str) -> bool:
        """Unregister a webhook and remove its listeners."""
        registration = self._webhooks.pop(webhook_id, None)
        if registration is None:
            return False
        # Remove the associated listeners (by identity is tricky, so we
        # just mark disabled — they'll short-circuit on next dispatch)
        registration.enabled = False
        self._save_webhooks()
        return True

    def list_webhooks(self) -> list[WebhookRegistration]:
        return sorted(self._webhooks.values(), key=lambda w: w.webhook_id)

    @staticmethod
    def _make_webhook_poster(registration: WebhookRegistration) -> HookListener:
        """Create an async listener that POSTs event payloads to a webhook URL."""

        async def _post_webhook(payload: dict[str, Any]) -> None:
            if not registration.enabled:
                return
            import aiohttp

            headers: dict[str, str] = {"Content-Type": "application/json"}
            if registration.secret:
                import hashlib
                import hmac

                body_bytes = json.dumps(payload, default=str).encode()
                sig = hmac.new(registration.secret.encode(), body_bytes, hashlib.sha256).hexdigest()
                headers["X-Hook-Signature"] = sig

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        registration.url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status >= 400:
                            logger.warning(
                                "Webhook %s returned %s for event %s",
                                registration.webhook_id,
                                resp.status,
                                payload.get("event"),
                            )
            except Exception:
                logger.exception(
                    "Webhook %s delivery failed for event %s",
                    registration.webhook_id,
                    payload.get("event"),
                )

        return _post_webhook

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(self, event: str, payload: dict[str, Any] | None = None) -> int:
        """Fire all enabled hooks and registered listeners for *event*.

        Returns the count of callbacks invoked.  Each listener is called
        in a fire-and-forget style for async callables (scheduled on the
        running event loop) and synchronously for plain functions.  Errors
        in individual listeners are logged but never propagate to the
        caller — dispatch must remain non-blocking.

        Additionally bridges events to the WebSocket channel layer so all
        connected frontend clients receive real-time updates.
        """
        effective_payload: dict[str, Any] = {"event": event, **(payload or {})}
        invoked = 0

        # 1. Check hook bindings for enabled state
        enabled_events = {binding.event for binding in self._bindings.values() if binding.enabled}

        # 2. Registered listeners
        for listener in self._listeners.get(event, []):
            # If hook bindings exist for this event, skip dispatch when disabled
            if self._bindings and event in {b.event for b in self._bindings.values()} and event not in enabled_events:
                continue
            try:
                result = listener(effective_payload)
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self._safe_async_invoke(listener, result))
                    except RuntimeError:
                        # No running loop — close the coroutine to avoid un-awaited warnings.
                        result.close()
                        logger.debug("No event loop for async hook listener on %s", event)
                invoked += 1
            except Exception:
                logger.exception("Hook listener error for event %s", event)

        # 3. Bridge to WebSocket channel layer for real-time frontend push
        self._bridge_to_channel(event, effective_payload)

        if invoked:
            logger.debug("Dispatched event %s to %d listeners", event, invoked)
        return invoked

    # ------------------------------------------------------------------
    # Named lifecycle emitters
    # ------------------------------------------------------------------

    def emit_agent_status_changed(self, task_id: str, agent_id: str, status: str) -> int:
        return self.dispatch(
            EVENT_AGENT_STATUS_CHANGED,
            {"task_id": task_id, "agent_id": agent_id, "status": status},
        )

    def emit_handoff_created(self, task_id: str, agent_id: str, session_id: str) -> int:
        return self.dispatch(
            EVENT_HANDOFF_CREATED,
            {"task_id": task_id, "agent_id": agent_id, "session_id": session_id},
        )

    def emit_execution_started(
        self,
        task_id: str,
        agent_id: str,
        *,
        query_session_id: str | None = None,
        status: str = "running",
    ) -> int:
        return self.dispatch(
            EVENT_EXECUTION_STARTED,
            {
                "task_id": task_id,
                "agent_id": agent_id,
                "query_session_id": query_session_id,
                "status": status,
            },
        )

    def emit_execution_completed(
        self,
        task_id: str,
        *,
        source: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        event_payload: dict[str, Any] = {"task_id": task_id, **(payload or {})}
        if source is not None:
            event_payload["source"] = source
        return self.dispatch(EVENT_EXECUTION_COMPLETED, event_payload)

    def emit_task_completed(self, task_id: str, payload: dict[str, Any] | None = None) -> int:
        return self.dispatch(EVENT_TASK_COMPLETED, {"task_id": task_id, **(payload or {})})

    def emit_task_failed(self, task_id: str, payload: dict[str, Any] | None = None) -> int:
        return self.dispatch(EVENT_TASK_FAILED, {"task_id": task_id, **(payload or {})})

    def emit_agents_terminated(self, task_id: str, payload: dict[str, Any] | None = None) -> int:
        return self.dispatch(EVENT_AGENTS_TERMINATED, {"task_id": task_id, **(payload or {})})

    def emit_agent_updated(self, task_id: str, agent_id: str) -> int:
        return self.dispatch(EVENT_AGENT_UPDATED, {"task_id": task_id, "agent_id": agent_id})

    def emit_capability_refresh(self, payload: dict[str, Any] | None = None) -> int:
        return self.dispatch(EVENT_CAPABILITY_REFRESH, payload or {})

    # ------------------------------------------------------------------
    # WebSocket channel bridge
    # ------------------------------------------------------------------

    # Map HookCore event names → channel_sdk ChannelEventType values
    _HOOK_TO_CHANNEL: dict[str, str] = {
        EVENT_TASK_COMPLETED: "task.completed",
        EVENT_TASK_FAILED: "task.failed",
        EVENT_AGENT_STATUS_CHANGED: "agent.status_changed",
        EVENT_AGENT_UPDATED: "agent.updated",
        EVENT_AGENTS_TERMINATED: "agents.terminated",
        EVENT_HANDOFF_CREATED: "handoff.created",
        EVENT_EXECUTION_STARTED: "execution.started",
        EVENT_EXECUTION_COMPLETED: "execution.completed",
        EVENT_WORKSPACE_CREATED: "workspace.created",
        EVENT_WORKSPACE_UPDATED: "workspace.updated",
        EVENT_CAPABILITY_REFRESH: "capability.refresh",
        EVENT_CHANNEL_MESSAGE: "channel.message",
    }

    def _bridge_to_channel(self, event: str, payload: dict[str, Any]) -> None:
        """Forward a hook event to the WebSocket channel layer (fire-and-forget)."""
        channel_type_val = self._HOOK_TO_CHANNEL.get(event)
        if channel_type_val is None:
            return
        try:
            from src.gateway.channel_sdk import ChannelEvent, ChannelEventType
            from src.gateway.routers.ws_events import get_ws_channel_manager

            channel_event = ChannelEvent(
                event_type=ChannelEventType(channel_type_val),
                payload=payload,
                source="hook_core",
            )
            loop = asyncio.get_running_loop()
            loop.create_task(get_ws_channel_manager().broadcast(channel_event))
        except (RuntimeError, ImportError, ValueError):
            # No running event loop, module not imported, or invalid event type
            pass
        except Exception:
            logger.debug("Channel bridge failed for event %s", event, exc_info=True)

    @staticmethod
    async def _safe_async_invoke(listener: HookListener, coro) -> None:
        try:
            await coro
        except Exception:
            logger.exception("Async hook listener error: %s", listener)

    # ------------------------------------------------------------------
    # State introspection
    # ------------------------------------------------------------------

    def runtime_state(self) -> dict[str, object]:
        bindings = self.list_runtime_hooks()
        listener_counts = {event: len(cbs) for event, cbs in self._listeners.items() if cbs}
        webhooks = self.list_webhooks()
        return {
            "total_hooks": len(bindings),
            "enabled_hooks": sum(1 for item in bindings if item.enabled),
            "events": sorted({item.event for item in bindings} | set(self._listeners.keys())),
            "listeners": listener_counts,
            "total_webhooks": len(webhooks),
            "enabled_webhooks": sum(1 for w in webhooks if w.enabled),
        }

    # ------------------------------------------------------------------
    # Hook inventory / config
    # ------------------------------------------------------------------

    @staticmethod
    def _repo_root() -> Path:
        return get_skills_root_path().parent

    @classmethod
    def _hooks_root(cls) -> Path:
        return cls._repo_root() / "tools" / "hooks"

    @staticmethod
    def _extract_description(hook_dir: Path) -> str:
        readme_path = hook_dir / "README.md"
        if not readme_path.exists():
            return ""
        lines = [line.strip() for line in readme_path.read_text(encoding="utf-8").splitlines()]
        if lines and lines[0] == "---":
            for line in lines[1:]:
                if line == "---":
                    break
                if line.startswith("description:"):
                    return line.split(":", 1)[1].strip().strip("'\"")
        for line in lines:
            if line and line != "---" and not line.startswith(("#", "name:", "description:", "tags:")):
                return line
        return ""

    @staticmethod
    def _read_manifest(hook_dir: Path) -> dict[str, Any]:
        manifest_path = hook_dir / "hooks.json"
        if not manifest_path.exists():
            return {}
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse %s: %s", manifest_path, exc)
            return {}
        return payload if isinstance(payload, dict) else {}

    def list_available_hooks(self) -> list[dict[str, Any]]:
        hooks_root = self._hooks_root()
        if not hooks_root.exists():
            return []

        config = get_extensions_config()
        responses: list[dict[str, Any]] = []
        for hook_dir in sorted(entry for entry in hooks_root.iterdir() if entry.is_dir()):
            manifest = self._read_manifest(hook_dir)
            trigger_map = manifest.get("hooks") if isinstance(manifest, dict) else {}
            triggers: list[dict[str, Any]] = []
            if isinstance(trigger_map, dict):
                for trigger, actions in trigger_map.items():
                    triggers.append(
                        {
                            "trigger": str(trigger),
                            "command_count": len(actions) if isinstance(actions, list) else 0,
                        }
                    )
            files = sorted(entry.name for entry in hook_dir.iterdir() if entry.is_file())
            responses.append(
                {
                    "name": hook_dir.name,
                    "description": self._extract_description(hook_dir),
                    "enabled": config.is_hook_enabled(hook_dir.name),
                    "triggers": sorted(triggers, key=lambda item: item["trigger"]),
                    "files": files,
                }
            )
        return responses

    def set_hook_enabled(self, hook_name: str, enabled: bool) -> dict[str, Any] | None:
        hook_dir = self._hooks_root() / hook_name
        if not hook_dir.exists() or not hook_dir.is_dir():
            return None

        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            config_path = self._repo_root() / "extensions_config.json"

        config = get_extensions_config()
        config.hooks[hook_name] = HookStateConfig(enabled=enabled)
        config_path.write_text(
            json.dumps(config.to_serializable_dict(), indent=2),
            encoding="utf-8",
        )

        reloaded = reload_extensions_config()
        self.dispatch(
            EVENT_CAPABILITY_REFRESH,
            {"category": "hooks", "hook_name": hook_name, "enabled": enabled},
        )
        return next(
            (item for item in self.list_available_hooks() if item["name"] == hook_name),
            {
                "name": hook_name,
                "description": self._extract_description(hook_dir),
                "enabled": reloaded.is_hook_enabled(hook_name),
                "triggers": [],
                "files": sorted(entry.name for entry in hook_dir.iterdir() if entry.is_file()),
            },
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _webhooks_path(self) -> Path | None:
        if self._store_dir is None:
            return None
        return self._store_dir / self._WEBHOOKS_FILE

    def _save_webhooks(self) -> None:
        """Persist current webhook registrations to disk."""
        path = self._webhooks_path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(w) for w in self._webhooks.values()]
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
        logger.debug("Saved %d webhook registrations to %s", len(data), path)

    def _load_webhooks(self) -> None:
        """Load webhook registrations from disk and re-wire listeners."""
        path = self._webhooks_path()
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for item in data:
                reg = WebhookRegistration(
                    webhook_id=item["webhook_id"],
                    url=item["url"],
                    events=item.get("events", []),
                    enabled=item.get("enabled", True),
                    secret=item.get("secret"),
                    metadata=item.get("metadata", {}),
                )
                self._webhooks[reg.webhook_id] = reg
                for event in reg.events:
                    self.on(event, self._make_webhook_poster(reg))
            logger.info("Loaded %d webhook registrations from %s", len(data), path)
        except Exception:
            logger.exception("Failed to load webhook registrations from %s", path)


_service: HookCoreService | None = None


def get_hook_core_service() -> HookCoreService:
    global _service
    if _service is None:
        store_dir: Path | None = None
        try:
            from src.runtime.config import get_paths

            store_dir = get_paths().hooks_store_dir
        except Exception:
            pass
        _service = HookCoreService(store_dir=store_dir)
    return _service


__all__ = ["HookCoreService", "RuntimeHookBinding", "get_hook_core_service"]
