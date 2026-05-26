from __future__ import annotations

from src.models.factory import _model_settings_exclude_fields


def test_model_auth_metadata_is_not_forwarded_to_provider_constructor() -> None:
    excluded = _model_settings_exclude_fields()

    assert "auth_mode" in excluded
    assert "conversation_url" in excluded
    assert "source" in excluded
