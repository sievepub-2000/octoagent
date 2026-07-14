from src.models.embedding_service import _resolve_cached_model_path


def test_hf_home_resolves_standard_hub_subdirectory(tmp_path, monkeypatch) -> None:
    snapshot = tmp_path / "hub" / "models--Qwen--Qwen3-Embedding-0.6B" / "snapshots" / "revision"
    snapshot.mkdir(parents=True)
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.delenv("SENTENCE_TRANSFORMERS_HOME", raising=False)

    assert _resolve_cached_model_path("Qwen/Qwen3-Embedding-0.6B") == snapshot


def test_missing_hf_home_cache_falls_back_to_project_cache(tmp_path, monkeypatch) -> None:
    project_hub = tmp_path / "project-hub"
    snapshot = project_hub / "models--Qwen--Qwen3-Embedding-0.6B" / "snapshots" / "revision"
    snapshot.mkdir(parents=True)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "empty-hf-home"))
    monkeypatch.delenv("SENTENCE_TRANSFORMERS_HOME", raising=False)
    monkeypatch.setattr(
        "src.models.embedding_service.Path.home",
        lambda: tmp_path / "empty-home",
    )
    monkeypatch.setattr(
        "src.models.embedding_service._PROJECT_HF_HUB",
        project_hub,
    )

    assert _resolve_cached_model_path("Qwen/Qwen3-Embedding-0.6B") == snapshot
