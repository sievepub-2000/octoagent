from __future__ import annotations

from src.runtime.config import app_config, paths


def test_default_model_config_is_cached_until_file_changes(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("system:\n  default_model: first\n", encoding="utf-8")
    monkeypatch.setattr(app_config, "resolve_app_config_path", lambda: config_file)
    paths._read_system_default_model.cache_clear()

    calls = 0
    original_safe_load = paths.yaml.safe_load

    def counted_safe_load(stream):
        nonlocal calls
        calls += 1
        return original_safe_load(stream)

    monkeypatch.setattr(paths.yaml, "safe_load", counted_safe_load)

    assert paths._load_system_default_model_from_config() == "first"
    assert paths._load_system_default_model_from_config() == "first"
    assert calls == 1

    config_file.write_text("system:\n  default_model: second-model\n", encoding="utf-8")
    assert paths._load_system_default_model_from_config() == "second-model"
    assert calls == 2
