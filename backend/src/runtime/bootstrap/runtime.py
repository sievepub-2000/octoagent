"""Embedded tiny-model runtime based on llama.cpp."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

from huggingface_hub import hf_hub_download
from langchain_core.messages import BaseMessage
from llama_cpp import Llama

from src.runtime.config.embedded_model_config import get_embedded_model_config
from src.runtime.config.paths import get_paths
from src.storage.rag import get_unified_rag_store

from .semantic_store import BootstrapSemanticStore

_runtime: EmbeddedBootstrapRuntime | None = None


class EmbeddedBootstrapRuntime:
    def __init__(self):
        self._config = get_embedded_model_config()
        self._llm: Llama | None = None

    @staticmethod
    def repo_root() -> Path:
        return Path(__file__).resolve().parents[4]

    @property
    def config(self):
        return self._config

    def model_cache_dir(self) -> Path:
        configured = Path(self._config.cache_dir)
        if configured.is_absolute():
            return configured
        if self._config.project_managed:
            return self.repo_root() / configured
        return get_paths().base_dir / configured

    def model_path(self) -> Path:
        return self.model_cache_dir() / self._config.filename

    def vector_store_path(self) -> Path:
        return get_unified_rag_store().db_path

    def semantic_store(self) -> BootstrapSemanticStore:
        return BootstrapSemanticStore(self.vector_store_path())

    def is_installed(self) -> bool:
        return self.model_path().exists()

    def ensure_installed(self) -> Path:
        self.model_cache_dir().mkdir(parents=True, exist_ok=True)
        if self.model_path().exists():
            return self.model_path()
        downloaded = hf_hub_download(
            repo_id=self._config.repo_id,
            filename=self._config.filename,
            local_dir=str(self.model_cache_dir()),
            local_dir_use_symlinks=False,
        )
        return Path(downloaded)

    def status(self) -> dict[str, Any]:
        path = self.model_path()
        stats = self.semantic_store().stats()
        corpus_files = self._local_corpus_files()
        return {
            "enabled": self._config.enabled,
            "project_managed": self._config.project_managed,
            "framework": self._config.framework,
            "repo_id": self._config.repo_id,
            "filename": self._config.filename,
            "model_path": str(path),
            "installed": path.exists(),
            "onboarding_enabled": self._config.onboarding_enabled,
            "use_for_embeddings": self._config.use_for_embeddings,
            "vector_store_path": str(self.vector_store_path()),
            "starter_prompts": self._config.starter_prompts,
            "documents": stats["documents"],
            "namespaces": stats["namespaces"],
            "n_ctx": self._config.n_ctx,
            "n_batch": self._config.n_batch,
            "n_threads": self._config.n_threads,
            "recommended_model": "Gemma 4 E2B IT GGUF Q8_0",
            "size_bytes": path.stat().st_size if path.exists() else None,
            "corpus_files": [str(item) for item in corpus_files],
        }

    def _load_llm(self) -> Llama:
        if self._llm is None:
            if not self.is_installed():
                if self._config.auto_download:
                    self.ensure_installed()
                else:
                    raise FileNotFoundError(f"Embedded model file not found at {self.model_path()}. Install it first.")
            self._llm = Llama(
                model_path=str(self.model_path()),
                n_ctx=self._config.n_ctx,
                n_threads=min(self._config.n_threads, os.cpu_count() or self._config.n_threads),
                n_batch=self._config.n_batch,
                embedding=False,
                verbose=False,
            )
        return self._llm

    def generate_guide(
        self,
        *,
        user_goal: str | None = None,
        workspace_summary: str | None = None,
    ) -> dict[str, Any]:
        llm = self._load_llm()
        retrieved_context = ""
        retrieved_items: list[str] = []
        if not retrieved_items and self._config.use_for_embeddings:
            try:
                query_embedding = self.embed_text(user_goal or "首次使用 OctoAgent 的本地部署与工作流引导")
                matches = []
                for namespace in ("onboarding", "local_docs"):
                    matches.extend(
                        self.semantic_store().search(
                            namespace=namespace,
                            query_embedding=query_embedding,
                            top_k=self._config.retrieval_top_k,
                        )
                    )
                matches.sort(key=lambda item: item.score, reverse=True)
                if matches:
                    retrieved_items = [match.content for match in matches[: self._config.retrieval_top_k]]
                    retrieved_context = "\n".join(f"- {item}" for item in retrieved_items)
            except Exception:
                retrieved_context = ""
        system_prompt = (
            "You are OctoAgent's embedded bootstrap guide. "
            "Respond in the user's language and default to English when unclear. "
            "Prioritize safe local setup, explain the next 2-4 actions, "
            "and avoid pretending the system can do things that are not configured. "
            "Do not invent UI buttons, menus, or capabilities. "
            "Only mention features explicitly present in the provided context."
        )
        user_prompt = (
            f"用户目标: {user_goal or '首次进入系统，需要初始化引导'}\n"
            f"工作区状态: {workspace_summary or '多 agent、本地部署、可选工作流与工具执行'}\n"
            f"已知系统能力:\n{retrieved_context or '- 当前已启用流式对话、工作流卡片、运行时保护和本地模型回退'}\n"
            "Output:\n"
            "1. one short startup guide\n"
            "2. three suggested messages the user can send to the main agent\n"
            "Do not invent buttons, pages, or capabilities that are not in the context."
        )
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
            top_p=self._config.top_p,
        )
        content = response["choices"][0]["message"]["content"].strip()
        return {
            "message": content,
            "suggestions": self._build_starter_suggestions(
                user_goal=user_goal,
                retrieved_items=retrieved_items,
            ),
            "evidence": retrieved_items,
        }

    def emergency_chat(
        self,
        messages: list[BaseMessage],
        *,
        emergency_reason: str,
    ) -> dict[str, str]:
        llm = self._load_llm()
        runtime_messages = _normalize_emergency_messages(messages, emergency_reason=emergency_reason)

        response = llm.create_chat_completion(
            messages=runtime_messages,
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
            top_p=self._config.top_p,
        )
        content = response["choices"][0]["message"]["content"].strip()
        return {"message": content}

    def embed_text(self, text: str) -> list[float]:
        return get_unified_rag_store().embed_one(text)

    def seed_default_documents(self) -> dict[str, int]:
        namespace = "onboarding"
        docs = [
            {
                "id": f"seed-{uuid.uuid4()}",
                "content": "Task 适合单链主控任务，Branch 适合并行分工，Group 只适合需要讨论和主控收口的场景。",
                "metadata": {"kind": "workflow"},
            },
            {
                "id": f"seed-{uuid.uuid4()}",
                "content": "本地部署时应优先控制 agent 并发和分支宽度，避免内存守卫触发或本地模型抖动。",
                "metadata": {"kind": "safety"},
            },
            {
                "id": f"seed-{uuid.uuid4()}",
                "content": "当模型超时、429 或网络错误时，应提示用户并自动切换到配置的 fallback model。",
                "metadata": {"kind": "fallback"},
            },
        ]
        prepared = []
        for item in docs:
            prepared.append(
                {
                    **item,
                }
            )
        store = self.semantic_store()
        store.upsert_documents(namespace, prepared)
        return store.stats()

    def sync_local_corpus(self) -> dict[str, int]:
        project_root = Path(__file__).resolve().parents[4]
        documents = []
        for path in self._local_corpus_files():
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            relative_source = str(path.relative_to(project_root)) if path.is_relative_to(project_root) else str(path)
            for index, chunk in enumerate(_chunk_markdown(content)):
                documents.append(
                    {
                        "id": f"doc-{path.name}-{index}",
                        "content": chunk,
                        "metadata": {"source": relative_source},
                    }
                )
        if documents:
            self.semantic_store().upsert_documents("local_docs", documents)
        return self.semantic_store().stats()

    def _local_corpus_files(self) -> list[Path]:
        project_root = Path(__file__).resolve().parents[4]
        candidates = [
            project_root / "README.md",
            project_root / "project_docs" / "docs" / "PROJECT_STATUS.md",
            project_root / "project_docs" / "docs" / "PROJECT_PROGRESS.md",
            project_root / "project_docs" / "docs" / "P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md",
            project_root / "frontend" / "src" / "components" / "workspace" / "settings" / "about.md",
        ]
        return [path for path in candidates if path.exists()]

    def _build_starter_suggestions(
        self,
        *,
        user_goal: str | None,
        retrieved_items: list[str],
    ) -> list[str]:
        suggestions = list(self._config.starter_prompts)
        if user_goal:
            suggestions.insert(0, f"围绕这个目标给我最稳妥的起步方案：{user_goal}")
        for item in retrieved_items[:2]:
            short = re.sub(r"\s+", " ", item).strip()
            suggestions.append(f"基于这条系统能力继续展开：{short[:80]}")
        seen = set()
        deduped = []
        for item in suggestions:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped[:4]


def _chunk_markdown(content: str, chunk_size: int = 360) -> list[str]:
    normalized = re.sub(r"\n{3,}", "\n\n", content)
    paragraphs = [part.strip() for part in normalized.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= chunk_size:
            current = paragraph
            continue
        for start in range(0, len(paragraph), chunk_size):
            chunks.append(paragraph[start : start + chunk_size])
        current = ""
    if current:
        chunks.append(current)
    return chunks


def _normalize_emergency_messages(
    messages: list[BaseMessage],
    *,
    emergency_reason: str,
) -> list[dict[str, str]]:
    system_preamble = (
        "You are OctoAgent's embedded emergency fallback model. "
        "Reply in the user's language and default to English when unclear. "
        "First state briefly that the system has switched to the embedded backup model "
        f"because: {emergency_reason}. Then continue helping with the current request in a concise way. "
        "Remind the user to reconfigure the primary model in settings if needed."
    )

    normalized: list[dict[str, str]] = []
    carry_system = system_preamble

    for message in messages[-12:]:
        content = str(message.content).strip()
        if not content:
            continue

        if message.type in {"system"}:
            carry_system = f"{carry_system}\n\nAdditional system context:\n{content}"
            continue

        role = "assistant"
        if message.type in {"human", "user"}:
            role = "user"

        if role == "user" and carry_system:
            content = f"{carry_system}\n\nCurrent user request:\n{content}"
            carry_system = ""

        if normalized and normalized[-1]["role"] == role:
            normalized[-1]["content"] = f"{normalized[-1]['content']}\n\n{content}"
            continue

        normalized.append({"role": role, "content": content})

    if not normalized:
        normalized.append(
            {
                "role": "user",
                "content": (f"{carry_system}\n\nCurrent user request:\nThe main model is unavailable. Continue the conversation helpfully."),
            }
        )
    elif normalized[0]["role"] != "user":
        normalized.insert(
            0,
            {
                "role": "user",
                "content": (f"{carry_system}\n\nConversation context follows. Continue helpfully."),
            },
        )
        carry_system = ""
    elif carry_system:
        normalized[0]["content"] = f"{carry_system}\n\n{normalized[0]['content']}"
        carry_system = ""

    if normalized[-1]["role"] != "user":
        normalized.append(
            {
                "role": "user",
                "content": "Continue from the conversation context above and provide the next helpful response.",
            }
        )

    return normalized


def get_embedded_bootstrap_runtime() -> EmbeddedBootstrapRuntime:
    global _runtime
    if _runtime is None:
        _runtime = EmbeddedBootstrapRuntime()
    return _runtime
