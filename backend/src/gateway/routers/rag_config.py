"""Runtime RAG config router."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.runtime.config.effective import (
    RagConfig,
    apply_rag_config,
    initialize_runtime_config,
    load_rag_config,
    model_cache_status,
    rag_config_path,
    save_rag_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runtime/rag-config", tags=["rag-config"])

# Keep legacy import-time behaviour for processes that import only this router.
initialize_runtime_config()


@router.get("")
def get_config() -> dict[str, Any]:
    cfg = load_rag_config()
    return {
        "config": cfg.model_dump(),
        "embedding_status": model_cache_status(cfg.embedding_model),
        "reranker_status": model_cache_status(cfg.reranker_model),
        "config_file": str(rag_config_path().resolve()),
    }


@router.put("")
def put_config(payload: RagConfig) -> dict[str, Any]:
    save_rag_config(payload)
    apply_rag_config(payload)
    logger.info(
        "RAG config updated: embedding=%s reranker_enabled=%s reranker=%s",
        payload.embedding_model,
        payload.reranker_enabled,
        payload.reranker_model,
    )
    return {
        "ok": True,
        "config": payload.model_dump(),
        "embedding_status": model_cache_status(payload.embedding_model),
        "reranker_status": model_cache_status(payload.reranker_model),
    }


class DownloadRequest(BaseModel):
    model: str
    kind: str = Field(pattern="^(embedding|reranker)$")


@router.post("/download")
def download_model(req: DownloadRequest) -> dict[str, Any]:
    """Trigger a HF Hub snapshot download for the given model."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"huggingface_hub not installed: {exc}") from exc
    try:
        path = snapshot_download(repo_id=req.model)
        return {"ok": True, "model": req.model, "kind": req.kind, "path": path}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
