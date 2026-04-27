import json
from dataclasses import dataclass

from src.models import factory


@dataclass
class FakeModel:
    name: str
    supports_thinking: bool = False
    supports_vision: bool = False
    max_context_tokens: int | None = None
    priority: int = 0
    profile_tags: list[str] | None = None


class FakeConfig:
    def __init__(self, models: list[FakeModel]):
        self.models = models

    def get_model_config(self, name: str):
        return next((model for model in self.models if model.name == name), None)


def test_default_model_selection_prefers_persisted_setup_state(monkeypatch, tmp_path):
    setup_state = tmp_path / "setup.json"
    setup_state.write_text(
        json.dumps({"default_model": "configured-default"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("OCTO_AGENT_SETUP_STATE_FILE", str(setup_state))
    monkeypatch.setattr(
        factory,
        "get_app_config",
        lambda: FakeConfig(
            [
                FakeModel("high-priority", priority=100),
                FakeModel("configured-default", priority=0),
            ]
        ),
    )

    selected = factory._select_default_model_name(
        thinking_enabled=False,
        selection_profile="default",
        requires_vision=False,
        min_context_tokens=None,
    )

    assert selected == "configured-default"


def test_default_model_selection_falls_back_when_persisted_model_lacks_required_capability(
    monkeypatch,
    tmp_path,
):
    setup_state = tmp_path / "setup.json"
    setup_state.write_text(
        json.dumps({"default_model": "text-only"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("OCTO_AGENT_SETUP_STATE_FILE", str(setup_state))
    monkeypatch.setattr(
        factory,
        "get_app_config",
        lambda: FakeConfig(
            [
                FakeModel("text-only", supports_vision=False, priority=100),
                FakeModel("vision-model", supports_vision=True, priority=1),
            ]
        ),
    )

    selected = factory._select_default_model_name(
        thinking_enabled=False,
        selection_profile="default",
        requires_vision=True,
        min_context_tokens=None,
    )

    assert selected == "vision-model"
