import os

from src.runtime.config.app_config import load_project_dotenv


def test_managed_model_secrets_are_loaded_on_startup(monkeypatch, tmp_path) -> None:
    secrets_file = tmp_path / "models.env"
    secrets_file.write_text("OCTOAGENT_MODEL_RESTART_TEST_API_KEY=persisted\n", encoding="utf-8")
    monkeypatch.setenv("OCTOAGENT_MANAGED_SECRETS_FILE", str(secrets_file))
    monkeypatch.delenv("OCTOAGENT_MODEL_RESTART_TEST_API_KEY", raising=False)

    load_project_dotenv()

    assert os.environ["OCTOAGENT_MODEL_RESTART_TEST_API_KEY"] == "persisted"
