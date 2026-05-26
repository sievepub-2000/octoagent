from __future__ import annotations

import os

from src.runtime.config.effective import RagConfig, apply_rag_config, load_rag_config, rag_config_path, save_rag_config


def test_rag_config_round_trips_through_runtime_store(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "rag_config.json"
    monkeypatch.setenv("OCTOAGENT_RAG_CONFIG_FILE", str(config_file))
    cfg = RagConfig(
        embedding_model="sentence-transformers/test",
        reranker_enabled=True,
        reranker_model="BAAI/test-reranker",
        top_k_default=7,
    )

    save_rag_config(cfg)
    loaded = load_rag_config()

    assert rag_config_path() == config_file
    assert loaded == cfg


def test_apply_rag_config_updates_process_env(monkeypatch) -> None:
    cfg = RagConfig(
        embedding_model="sentence-transformers/env-test",
        reranker_enabled=True,
        reranker_model="BAAI/env-reranker",
        top_k_default=5,
    )

    apply_rag_config(cfg)

    assert os.environ["OCTOAGENT_EMBEDDING_MODEL"] == cfg.embedding_model
    assert os.environ["OCTOAGENT_RERANKER_MODEL"] == cfg.reranker_model
    assert os.environ["OCTOAGENT_RERANKER_ENABLED"] == "1"
