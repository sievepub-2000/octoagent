from __future__ import annotations

import threading
from types import SimpleNamespace

from src.runtime.system_guard import service as system_guard_service


def test_system_guard_skips_signal_handlers_outside_main_thread(monkeypatch):
    monkeypatch.setattr(
        system_guard_service,
        "get_system_guard_config",
        lambda: SimpleNamespace(
            enabled=True,
            capture_atexit=False,
            register_signal_handlers=True,
            vector_store_path="unused.duckdb",
        ),
    )

    errors: list[BaseException] = []

    def build_service() -> None:
        try:
            system_guard_service.SystemGuardService(store=object())
        except BaseException as exc:  # pragma: no cover - assertion reports the repr
            errors.append(exc)

    worker = threading.Thread(target=build_service, name="system-guard-test-worker")
    worker.start()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert errors == []
