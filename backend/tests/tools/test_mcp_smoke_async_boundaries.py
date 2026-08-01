from __future__ import annotations

import asyncio
import threading

from src.runtime.config.extensions_config import McpServerConfig
from src.tools.mcp import smoke


def test_schema_check_runs_off_the_event_loop(monkeypatch) -> None:
    event_loop_thread = threading.get_ident()
    schema_thread: list[int] = []

    def schema_check(name: str, config: McpServerConfig) -> dict[str, object]:
        schema_thread.append(threading.get_ident())
        return {"ok": True, "issues": [], "server": name}

    monkeypatch.setattr(smoke, "_schema_check", schema_check)
    result = asyncio.run(
        smoke.smoke_one_mcp_server(
            "disabled-audit",
            McpServerConfig(enabled=False, type="stdio", command="node"),
        )
    )

    assert result["overall_status"] == "disabled"
    assert schema_thread and schema_thread[0] != event_loop_thread
