"""System startup self-check and self-repair service."""

from __future__ import annotations

import atexit
import hashlib
import hmac
import json
import logging
import os
import signal
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType
from typing import Any

import duckdb

from src.runtime.config.app_config import AppConfig, get_app_config
from src.runtime.config.paths import get_paths, resolve_configured_default_model_name
from src.runtime.config.system_guard_config import get_system_guard_config
from src.utils.datetime import utc_now_iso as _utc_now

from .vector_store import SystemGuardVectorStore

logger = logging.getLogger(__name__)

RepairAgentCallable = Callable[[str], str]


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_file(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_embedding_from_text(text: str, dim: int = 64) -> list[float]:
    """Generate an embedding vector for the given text.

    Uses the unified EmbeddingService when available (sentence-transformers / llama.cpp),
    falling back to SHA-256 deterministic pseudo-embedding otherwise.
    """
    try:
        from src.models.embedding_service import get_embedding_service

        return get_embedding_service().embed_one(text)
    except Exception:
        # Fallback: SHA-256 deterministic pseudo-embedding
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector: list[float] = []
        for index in range(dim):
            value = digest[index % len(digest)]
            vector.append((float(value) / 255.0) * 2 - 1)
        return vector


def _pseudo_embedding_from_text(text: str, dim: int = 64) -> list[float]:
    """Generate a deterministic local-only pseudo embedding.

    This path is intentionally model-free so startup/shutdown snapshots remain
    reliable even when runtime embedding backends are unavailable or slow.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vector: list[float] = []
    for index in range(dim):
        value = digest[index % len(digest)]
        vector.append((float(value) / 255.0) * 2 - 1)
    return vector


class SystemGuardService:
    """Persist lifecycle state, run startup checks, and trigger self-repair."""

    def __init__(
        self,
        *,
        store: SystemGuardVectorStore | None = None,
        repair_agent: RepairAgentCallable | None = None,
        register_hooks: bool = True,
    ):
        self._config = get_system_guard_config()
        self._paths = get_paths()
        self._repair_agent = repair_agent
        self._store = store or self._build_store()
        self._session_id = str(uuid.uuid4())
        self._started_at = _utc_now()
        self._lock = threading.Lock()
        self._shutdown_persisted = False
        self._previous_signal_handlers: dict[int, Any] = {}
        self._signal_exit_reason: str | None = None
        self._config_path = self._resolve_config_path()
        self._base_dir = self._paths.base_dir

        if register_hooks and self._config.enabled:
            if self._config.capture_atexit:
                atexit.register(self._on_atexit)
            if self._config.register_signal_handlers:
                self._register_signal_handlers()

    def _resolve_config_path(self) -> Path | None:
        try:
            return AppConfig.resolve_config_path()
        except Exception:
            return None

    def _build_store(self) -> SystemGuardVectorStore:
        configured = Path(self._config.vector_store_path)
        db_path = configured if configured.is_absolute() else self._paths.base_dir / configured
        try:
            return SystemGuardVectorStore(db_path)
        except duckdb.Error:
            # Self-heal corrupted DB by moving away and recreating.
            backup = db_path.with_suffix(f".corrupted.{int(datetime.now(UTC).timestamp())}.bak")
            if db_path.exists():
                db_path.replace(backup)
                logger.warning("Moved corrupted system guard store to %s", backup)
            return SystemGuardVectorStore(db_path)

    def _register_signal_handlers(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            logger.info(
                "Skipping system guard signal handlers outside the main thread: thread=%s",
                threading.current_thread().name,
            )
            return

        for signum in (signal.SIGINT, signal.SIGTERM):
            previous = signal.getsignal(signum)
            self._previous_signal_handlers[signum] = previous
            signal.signal(signum, self._handle_signal)

    def _handle_signal(self, signum: int, frame: FrameType | None) -> None:
        signal_name = signal.Signals(signum).name
        # Keep signal-handler logic minimal and lock-free.
        # Final snapshot persistence is performed by graceful shutdown or atexit.
        self._signal_exit_reason = f"signal_{signal_name.lower()}"
        # SIGTERM/SIGINT are normal lifecycle events under systemd and Docker;
        # the subsequent graceful-shutdown snapshot is the relevant outcome.
        logger.info("System guard received signal %s", signal_name)

        previous = self._previous_signal_handlers.get(signum)
        if callable(previous):
            previous(signum, frame)
        elif previous == signal.SIG_DFL:
            raise SystemExit(128 + signum)

    def _on_atexit(self) -> None:
        self.shutdown(reason=self._signal_exit_reason or "atexit")

    def _config_overview(self) -> dict[str, Any]:
        try:
            app_config = get_app_config()
        except Exception as exc:
            return {"config_load_error": str(exc)}
        return {
            "default_model": resolve_configured_default_model_name(model.name for model in app_config.models),
            "models_count": len(app_config.models),
            "checkpointer_type": app_config.checkpointer.type if app_config.checkpointer else "none",
            "sandbox_provider": getattr(app_config.sandbox, "use", None),
        }

    def _run_startup_checks(self, previous_snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        overview = self._config_overview()
        if overview.get("models_count", 0) == 0:
            issues.append(
                {
                    "code": "no_models_configured",
                    "severity": "info",
                    "message": "No models are configured yet; complete model setup in the WebUI.",
                    "auto_repairable": False,
                }
            )

        if self._config_path is None or not self._config_path.exists():
            issues.append(
                {
                    "code": "config_missing",
                    "severity": "warning",
                    "message": "config.yaml was not resolved for startup.",
                    "auto_repairable": False,
                }
            )

        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            issues.append(
                {
                    "code": "base_dir_unwritable",
                    "severity": "critical",
                    "message": str(exc),
                    "auto_repairable": False,
                }
            )

        if previous_snapshot:
            prev = (previous_snapshot.get("state") or {}).get("config_overview") or {}
            drift = {}
            for key in ("default_model", "models_count", "checkpointer_type", "sandbox_provider"):
                if key in prev and prev.get(key) != overview.get(key):
                    drift[key] = {"previous": prev.get(key), "current": overview.get(key)}
            if drift:
                issues.append(
                    {
                        "code": "config_drift_detected",
                        "severity": "warning",
                        "message": "Current startup config differs from last recorded config.",
                        "auto_repairable": False,
                        "metadata": {"drift": drift},
                    }
                )
        return issues

    def _append_unclean_shutdown_issue(
        self,
        *,
        issues: list[dict[str, Any]],
        running_sessions: list[dict[str, Any]],
    ) -> None:
        if not running_sessions:
            return
        issues.append(
            {
                "code": "unclean_shutdown_detected",
                "severity": "warning",
                "message": "Previous session was not marked as stopped.",
                "auto_repairable": True,
                "metadata": {"running_sessions": running_sessions},
            }
        )

    def _call_default_agent_repair(self, issues: list[dict[str, Any]]) -> dict[str, Any]:
        if not self._should_invoke_default_agent(issues):
            return {"invoked": False}

        prompt = (
            "System startup self-check detected issues. "
            "Generate a concise self-repair plan with ordered steps.\n\n"
            f"Issues: {json.dumps(issues, ensure_ascii=False)}\n\n"
            "Output requirements:\n"
            "1) diagnosis\n2) immediate repair steps\n3) rollback steps\n"
            "Keep answer short and actionable."
        )

        def _invoke() -> str:
            if self._repair_agent is not None:
                return self._repair_agent(prompt)

            from src.interfaces.embedded.client import OctoAgentClient

            client = OctoAgentClient(thinking_enabled=False)
            return client.chat(
                prompt,
                thread_id=f"system-guard-repair-{self._session_id}",
                subagent_enabled=False,
            )

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_invoke)
                content = future.result(timeout=self._config.startup_agent_timeout_seconds)
            return {"invoked": True, "ok": True, "agent_plan": content}
        except TimeoutError:
            return {"invoked": True, "ok": False, "error": "default_agent_timeout"}
        except Exception as exc:  # noqa: BLE001
            return {"invoked": True, "ok": False, "error": str(exc)}

    def _run_deferred_startup_agent_repair(self, issues: list[dict[str, Any]]) -> None:
        result = self._call_default_agent_repair(issues)
        state = self._snapshot_state(
            phase="startup_agent_repair",
            issues=issues,
            repair_report={"default_agent": result},
            extra={"deferred": True},
        )
        persisted = self._persist_snapshot(phase="startup_agent_repair", state=state)
        logger.info(
            "Deferred startup agent repair finished: %s",
            {
                "session_id": self._session_id,
                "persisted": persisted,
                "result": result,
            },
        )

    def _schedule_startup_agent_repair(self, issues: list[dict[str, Any]]) -> dict[str, Any]:
        if not self._should_invoke_default_agent(issues):
            return {"invoked": False}

        worker = threading.Thread(
            target=self._run_deferred_startup_agent_repair,
            args=(list(issues),),
            daemon=True,
            name=f"system-guard-startup-agent-{self._session_id}",
        )
        worker.start()
        return {"invoked": False, "scheduled": True, "mode": "async"}

    def _should_invoke_default_agent(self, issues: list[dict[str, Any]]) -> bool:
        if not issues or not self._config.invoke_default_agent_on_issue:
            return False
        return any(issue.get("severity") == "critical" or issue.get("auto_repairable") is True for issue in issues)

    def _apply_builtin_repairs(
        self,
        issues: list[dict[str, Any]],
        *,
        close_reason: str,
    ) -> dict[str, Any]:
        actions: list[str] = []
        repaired = False

        stale_session_ids = []
        for issue in issues:
            if issue.get("code") != "unclean_shutdown_detected":
                continue
            metadata = issue.get("metadata") or {}
            for session in metadata.get("running_sessions") or []:
                session_id = session.get("session_id")
                if session_id:
                    stale_session_ids.append(session_id)

        if stale_session_ids:
            count = self._store.close_selected_running_sessions(
                session_ids=list(dict.fromkeys(stale_session_ids)),
                reason=close_reason,
                updated_at=_utc_now(),
            )
            actions.append(f"closed_stale_running_sessions={count}")
            repaired = repaired or count > 0

        return {"applied": repaired, "actions": actions}

    def _snapshot_state(
        self,
        *,
        phase: str,
        issues: list[dict[str, Any]],
        repair_report: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "session_id": self._session_id,
            "phase": phase,
            "timestamp": _utc_now(),
            "pid": os.getpid(),
            "config_path": str(self._config_path) if self._config_path else None,
            "config_hash": _hash_file(self._config_path),
            "config_overview": self._config_overview(),
            "issues": issues,
            "repair_report": repair_report or {},
            "extra": extra or {},
        }

    def _embedding_for_state(self, state: dict[str, Any]) -> tuple[str, list[float]]:
        content = f"phase={state.get('phase')} default_model={(state.get('config_overview') or {}).get('default_model')} issues={json.dumps(state.get('issues', []), ensure_ascii=False)}"
        if not self._config.runtime_embeddings_enabled:
            return content, _pseudo_embedding_from_text(content)
        try:
            from src.runtime.bootstrap.runtime import get_embedded_bootstrap_runtime

            runtime = get_embedded_bootstrap_runtime()
            if runtime.config.enabled and runtime.config.use_for_embeddings and runtime.is_installed():
                return content, runtime.embed_text(content)
        except Exception:
            pass
        return content, _stable_embedding_from_text(content)

    def _persist_snapshot(self, *, phase: str, state: dict[str, Any]) -> dict[str, Any]:
        content, embedding = self._embedding_for_state(state)
        snapshot_id = str(uuid.uuid4())
        metadata = {
            "phase": phase,
            "issues_count": len(state.get("issues") or []),
            "has_repair": bool(state.get("repair_report")),
        }
        self._store.insert_snapshot(
            snapshot_id=snapshot_id,
            session_id=self._session_id,
            namespace=self._config.namespace,
            phase=phase,
            created_at=state["timestamp"],
            content=content,
            metadata=metadata,
            state=state,
            embedding=embedding,
        )
        pruned = 0
        if self._config.max_snapshots_per_namespace is not None:
            pruned = self._store.prune_snapshots(
                namespace=self._config.namespace,
                keep_latest=self._config.max_snapshots_per_namespace,
            )
        return {
            "snapshot_id": snapshot_id,
            "phase": phase,
            "timestamp": state["timestamp"],
            "pruned_snapshots": pruned,
        }

    def startup_check_and_repair(self) -> dict[str, Any]:
        if not self._config.enabled:
            return {"enabled": False}

        previous_running = self._store.list_running_sessions()
        previous_snapshot = self._store.latest_snapshot()
        issues = self._run_startup_checks(previous_snapshot)
        self._append_unclean_shutdown_issue(
            issues=issues,
            running_sessions=previous_running,
        )

        builtin_repair = {"applied": False, "actions": []}
        if self._config.auto_repair:
            builtin_repair = self._apply_builtin_repairs(
                issues,
                close_reason="startup_recovery",
            )
        if self._config.startup_agent_async:
            agent_repair = self._schedule_startup_agent_repair(issues)
        else:
            agent_repair = self._call_default_agent_repair(issues)

        repair_report = {
            "builtin": builtin_repair,
            "default_agent": agent_repair,
        }
        state = self._snapshot_state(
            phase="startup_check",
            issues=issues,
            repair_report=repair_report,
        )
        persisted = self._persist_snapshot(phase="startup_check", state=state)
        self._store.mark_session(
            session_id=self._session_id,
            status="running",
            updated_at=state["timestamp"],
            state=state,
        )
        return {
            "ok": len([i for i in issues if i.get("severity") == "critical"]) == 0,
            "issues": issues,
            "repair_report": repair_report,
            "persisted": persisted,
            "session_id": self._session_id,
        }

    def run_manual_repair(self, *, advisory_only: bool = False) -> dict[str, Any]:
        if not self._config.enabled:
            return {"enabled": False}

        previous_snapshot = self._store.latest_snapshot()
        stale_running = [session for session in self._store.list_running_sessions() if session.get("session_id") != self._session_id]
        issues = self._run_startup_checks(previous_snapshot)
        self._append_unclean_shutdown_issue(
            issues=issues,
            running_sessions=stale_running,
        )

        builtin_repair = {"applied": False, "actions": []}
        if self._config.auto_repair and not advisory_only:
            builtin_repair = self._apply_builtin_repairs(
                issues,
                close_reason="manual_repair",
            )
        agent_repair = self._call_default_agent_repair(issues)

        repair_report = {
            "builtin": builtin_repair,
            "default_agent": agent_repair,
            "advisory_only": advisory_only,
        }
        state = self._snapshot_state(
            phase="manual_repair",
            issues=issues,
            repair_report=repair_report,
            extra={"advisory_only": advisory_only},
        )
        persisted = self._persist_snapshot(phase="manual_repair", state=state)
        self._store.mark_session(
            session_id=self._session_id,
            status="running",
            updated_at=state["timestamp"],
            state=state,
        )
        return {
            "ok": len([i for i in issues if i.get("severity") == "critical"]) == 0,
            "issues": issues,
            "repair_report": repair_report,
            "persisted": persisted,
            "session_id": self._session_id,
        }

    def shutdown(self, *, reason: str) -> dict[str, Any]:
        if not self._config.enabled:
            return {"enabled": False}
        final_reason = self._signal_exit_reason or reason
        with self._lock:
            if self._shutdown_persisted:
                return {"ok": True, "already_persisted": True, "session_id": self._session_id}
            state = self._snapshot_state(
                phase="shutdown",
                issues=[],
                extra={"reason": final_reason},
            )
            persisted = self._persist_snapshot(phase="shutdown", state=state)
            self._store.mark_session(
                session_id=self._session_id,
                status="stopped",
                updated_at=state["timestamp"],
                state=state,
            )
            self._shutdown_persisted = True
            return {"ok": True, "persisted": persisted, "session_id": self._session_id}

    def latest_snapshot(self) -> dict[str, Any] | None:
        return self._store.latest_snapshot()

    def recent_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._store.recent_snapshots(limit=limit)

    def retention_summary(self) -> dict[str, Any]:
        return {
            "namespace": self._config.namespace,
            "snapshot_count": self._store.count_snapshots(namespace=self._config.namespace),
            "retention_limit": self._config.max_snapshots_per_namespace,
        }

    def export_snapshots(self, *, limit: int = 20) -> dict[str, Any]:
        bounded_limit = max(1, min(limit, 100))
        retention = self.retention_summary()
        payload = {
            "namespace": self._config.namespace,
            "generated_at": _utc_now(),
            "latest_snapshot": self.latest_snapshot(),
            "recent_snapshots": self.recent_snapshots(limit=bounded_limit),
            "retention": retention,
        }
        canonical_payload = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

        signature_algorithm = "sha256"
        signed = False
        if self._config.export_signing_secret:
            signed = True
            signature_algorithm = "hmac-sha256"
            signature = hmac.new(
                self._config.export_signing_secret.encode("utf-8"),
                canonical_payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        elif self._config.require_signed_exports:
            raise ValueError("signed_export_unavailable")
        else:
            signature = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

        return {
            **payload,
            "signed": signed,
            "signature_algorithm": signature_algorithm,
            "signature": signature,
        }


_system_guard_service: SystemGuardService | None = None


def get_system_guard_service() -> SystemGuardService:
    global _system_guard_service
    if _system_guard_service is None:
        _system_guard_service = SystemGuardService()
    return _system_guard_service


def reset_system_guard_service() -> None:
    global _system_guard_service
    _system_guard_service = None
