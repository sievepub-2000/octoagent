from __future__ import annotations

import json

from src.agents.memory.global_memory import build_global_memory_prompt


def test_global_memory_is_rendered_for_runtime_injection(tmp_path, monkeypatch) -> None:
    memory_file = tmp_path / "global_memory.json"
    memory_file.write_text(
        json.dumps({"entries": [{"title": "Preference", "content": "Use concise Chinese."}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr("src.agents.memory.global_memory.global_memory_path", lambda: memory_file)

    prompt = build_global_memory_prompt()

    assert prompt is not None
    assert "Use concise Chinese." in prompt
    assert "latest user instructions still win" in prompt
