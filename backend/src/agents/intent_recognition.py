"""Intent recognition via embedding similarity (with keyword fallback).

Replaces rule-based intent matching with vector similarity when the
embedding service is available, falling back to keyword heuristics otherwise.
Opt-in via OCTOAGENT_INTENT_RECOGNITION=1.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _intent_recognition_enabled() -> bool:
    return os.environ.get("OCTOAGENT_INTENT_RECOGNITION", "0") == "1"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class IntentTemplate:
    """A registered intent with its description and optional prompt template."""

    name: str
    description: str
    template: str = ""
    keywords: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Default intents
# ---------------------------------------------------------------------------

_DEFAULT_INTENTS: dict[str, IntentTemplate] = {
    "code_development": IntentTemplate(
        name="code_development",
        description="Writing or modifying code — implementing features, refactoring, adding functions, editing files.",
        keywords=[
            "write code",
            "modify code",
            "implement",
            "refactor",
            "add function",
            "edit file",
            "create class",
            "update module",
            "code change",
            "programming",
            "develop feature",
            "fix syntax",
            "debug code",
            "source code",
        ],
    ),
    "debugging": IntentTemplate(
        name="debugging",
        description="Finding and fixing bugs — error investigation, stack trace analysis, issue diagnosis.",
        keywords=[
            "bug",
            "error",
            "fix bug",
            "debug",
            "stack trace",
            "exception",
            "crash",
            "fail",
            "issue",
            "problem",
            "diagnose",
            "trace",
            "broken",
            "not working",
            "throwing error",
            "runtime error",
            "why does",
            "what is wrong",
            "fix this",
            "help debug",
            "debug this",
            "error message",
            "exception trace",
        ],
    ),
    "deployment": IntentTemplate(
        name="deployment",
        description="Deploying applications — CI/CD, container orchestration, server configuration, releases.",
        keywords=[
            "deploy",
            "release",
            "push to production",
            "docker",
            "container",
            "kubernetes",
            "ci/cd",
            "pipeline",
            "build and deploy",
            "staging",
            "production",
            "server",
            "hosting",
            "infrastructure",
            "terraform",
        ],
    ),
    "documentation": IntentTemplate(
        name="documentation",
        description="Writing documentation — README, API docs, comments, guides, changelogs.",
        keywords=[
            "document",
            "readme",
            "api doc",
            "guide",
            "tutorial",
            "comment",
            "changelog",
            "writeup",
            "specification",
            "manual",
            "how-to",
            "documentation",
            "docs",
            "documentation update",
        ],
    ),
    "testing": IntentTemplate(
        name="testing",
        description="Writing or running tests — unit tests, integration tests, test execution, coverage.",
        keywords=[
            "test",
            "unit test",
            "integration test",
            "run tests",
            "coverage",
            "pytest",
            "jest",
            "spec",
            "assert",
            "mock",
            "fixture",
            "testing framework",
            "test suite",
            "e2e test",
            "smoke test",
        ],
    ),
    "research": IntentTemplate(
        name="research",
        description="Gathering information — web searches, documentation lookup, comparing options, learning.",
        keywords=[
            "search",
            "look up",
            "find out",
            "research",
            "explore",
            "compare",
            "documentation search",
            "web search",
            "investigate",
            "learn about",
            "what is",
            "how does",
            "alternative to",
            "best practice",
        ],
    ),
    "system_admin": IntentTemplate(
        name="system_admin",
        description="System configuration and maintenance — OS tasks, package management, user accounts, services.",
        keywords=[
            "install package",
            "configure",
            "service",
            "user account",
            "permission",
            "firewall",
            "network config",
            "disk space",
            "process",
            "cron job",
            "system update",
            "apt",
            "yum",
            "brew",
            "systemd",
            "environment variable",
        ],
    ),
}


# ---------------------------------------------------------------------------
# IntentRecognizer
# ---------------------------------------------------------------------------


class IntentRecognizer:
    """Embedding-based intent recognition with keyword fallback.

    Maintains a registry of intent templates, each with an embedding derived
    from its description (and keywords).  On recognise(), the user message is
    encoded and compared against all registered intents via cosine similarity.
    If no intent exceeds the threshold, falls back to keyword matching.
    """

    DEFAULT_THRESHOLD = 0.7

    def __init__(self) -> None:
        self._intents: dict[str, IntentTemplate] = {}
        self._embeddings: dict[str, list[float]] = {}
        self._embedding_service: Any = None
        self._threshold = self.DEFAULT_THRESHOLD
        self._initialized = False

    # ------------------------------------------------------------------ init

    def initialize(self) -> None:
        """Register default intents and build embeddings."""
        if self._initialized:
            return

        from src.models.embedding_service import get_embedding_service

        self._embedding_service = get_embedding_service()

        for name, template in _DEFAULT_INTENTS.items():
            self.register_intent(name, template.description, template.template)

        self._initialized = True
        logger.info("IntentRecognizer initialized with %d intents", len(self._intents))

    def register_intent(self, name: str, description: str, template: str = "") -> None:
        """Register a new intent with its embedding."""
        if not self._embedding_service:
            from src.models.embedding_service import get_embedding_service

            self._embedding_service = get_embedding_service()

        keywords = _extract_keywords(description)
        template_obj = IntentTemplate(name=name, description=description, template=template, keywords=keywords)
        self._intents[name] = template_obj

        # Build embedding from description + keywords
        embed_text = f"{description} {' '.join(keywords)}"
        try:
            self._embeddings[name] = self._embedding_service.embed_one(embed_text)
        except Exception as exc:
            logger.warning("Failed to embed intent '%s': %s", name, exc)

    # ------------------------------------------------------------------ recognize

    def recognise(self, user_message: str) -> dict[str, Any]:
        """Recognise the dominant intent in a user message.

        Returns a dict with keys:
            intent  — matched intent name (or None if below threshold)
            score   — cosine similarity (0.0–1.0)
            fallback — True if keyword matching was used instead of embeddings
        """
        if not self._initialized:
            self.initialize()

        # Try embedding-based recognition first
        try:
            result = self._recognize_by_embedding(user_message)
            if result["intent"] is not None:
                return result
        except Exception as exc:
            logger.debug("Embedding recognition failed, falling back to keywords: %s", exc)

        # Keyword fallback
        return self._recognize_by_keywords(user_message)

    def _recognize_by_embedding(self, user_message: str) -> dict[str, Any]:
        """Embedding-based intent matching."""
        query_vec = self._embedding_service.encode(user_message)

        best_name: str | None = None
        best_score = -1.0

        for name, emb in self._embeddings.items():
            score = self._embedding_service.cosine_similarity(query_vec, emb)
            if score > best_score:
                best_score = score
                best_name = name

        if best_name is None or best_score < self._threshold:
            return {"intent": None, "score": best_score, "fallback": False}

        template = self._intents[best_name]
        return {
            "intent": best_name,
            "description": template.description,
            "score": best_score,
            "fallback": False,
        }

    def _recognize_by_keywords(self, user_message: str) -> dict[str, Any]:
        """Keyword-based intent matching fallback."""
        msg_lower = user_message.lower()
        scores: dict[str, float] = {}

        for name, template in self._intents.items():
            matches = sum(1 for kw in template.keywords if kw in msg_lower)
            if matches > 0:
                # Weight by match count; a single keyword hit gets 0.4,
                # two hits get 0.6, three+ get 0.8 — never exceeds 1.0.
                scores[name] = min(0.3 + matches * 0.15, 1.0)

        if not scores:
            return {"intent": None, "score": 0.0, "fallback": True}

        best_name = max(scores, key=scores.get)
        template = self._intents[best_name]
        score = scores[best_name]

        return {
            "intent": best_name,
            "description": template.description,
            "score": score,
            "fallback": True,
        }

    # ------------------------------------------------------------------ registry

    def list_intents(self) -> list[str]:
        """Return all registered intent names."""
        if not self._initialized:
            self.initialize()
        return list(self._intents.keys())

    def get_intent(self, name: str) -> IntentTemplate | None:
        """Retrieve a specific intent template by name."""
        if not self._initialized:
            self.initialize()
        return self._intents.get(name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_keywords(description: str) -> list[str]:
    """Extract potential keyword phrases from an intent description."""
    # Split on common delimiters and keep tokens/phrases of reasonable length.
    cleaned = re.sub(r"[.,;:!?\(\)\[\]\-]", " ", description).lower()
    words = cleaned.split()
    keywords: list[str] = []

    # Two-word phrases that look like intent signals
    for i in range(len(words) - 1):
        phrase = f"{words[i]} {words[i + 1]}"
        if len(phrase) > 3 and not any(w in phrase for w in ("the", "a", "an", "of", "to", "in", "on", "is")):
            keywords.append(phrase)

    # Single meaningful words (length >= 4, skip common stopwords)
    stopwords = {"the", "a", "an", "of", "to", "in", "on", "is", "at", "by", "for", "with"}
    for w in words:
        if len(w) >= 4 and w not in stopwords and w not in keywords:
            keywords.append(w)

    return list(dict.fromkeys(keywords))[:20]


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_default_recognizer: IntentRecognizer | None = None


def get_intent_recognizer(**overrides: Any) -> IntentRecognizer:
    """Return the singleton IntentRecognizer (lazy-created, opt-in)."""
    global _default_recognizer
    if not _intent_recognition_enabled():
        logger.debug("Intent recognition disabled — set OCTOAGENT_INTENT_RECOGNITION=1 to enable")
        return None  # type: ignore[return-value]

    if _default_recognizer is None or overrides:
        _default_recognizer = IntentRecognizer(**overrides)  # type: ignore[arg-type]
    return _default_recognizer


__all__ = ["IntentRecognizer", "IntentTemplate", "get_intent_recognizer"]
