"""Middleware for automatic thread title generation.

Optimized v2: cache by thread_id so LLM is called at most once per thread,
skip entirely in flash mode (no titles needed for quick replies).
"""

import html
import re
import threading
from typing import NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from src.models import create_chat_model
from src.runtime.config.title_config import get_title_config


class TitleMiddlewareState(AgentState):
    """Compatible with the `ThreadState` schema."""

    title: NotRequired[str | None]


# Thread-safe cache: thread_id -> title string (set once, never changes)
_TITLE_CACHE: dict[str, str] = {}
_TITLE_CACHE_LOCK = threading.Lock()


class TitleMiddleware(AgentMiddleware[TitleMiddlewareState]):
    """Automatically generate a title for the thread after the first user message.

    Optimized v2: caches generated titles by thread_id so the LLM is invoked
    at most once per conversation. Skips entirely in flash mode.
    """

    state_schema = TitleMiddlewareState
    _PLACEHOLDER_TITLE_RE = re.compile(
        r"^(?:new\s+conversation|new\s+chat|untitled|chat(?:\s*[-+:：#]?\s*[a-z0-9_-]{4,})?)$",
        re.IGNORECASE,
    )

    @staticmethod
    def _sanitize_text(value: str) -> str:
        cleaned = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.IGNORECASE)
        cleaned = re.sub(r"<script[\s\S]*?</script>", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = html.unescape(cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _to_text(content: object) -> str:
        if isinstance(content, str):
            return TitleMiddleware._sanitize_text(content)
        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        cleaned = TitleMiddleware._sanitize_text(text)
                        if cleaned:
                            text_parts.append(cleaned)
            return "\n".join(text_parts)
        return TitleMiddleware._sanitize_text(str(content)) if content else ""

    @staticmethod
    def _build_prompt(state: TitleMiddlewareState) -> tuple[str, str]:
        """Build title prompt and keep first user message for fallback."""
        config = get_title_config()
        messages = state.get("messages", [])

        # Get first user message and first assistant response
        user_msg_content = next((m.content for m in messages if m.type == "human"), "")
        assistant_msg_content = next((m.content for m in messages if m.type == "ai"), "")

        # Ensure content is string (LangChain messages can have list content)
        user_msg = TitleMiddleware._to_text(user_msg_content)
        assistant_msg = TitleMiddleware._to_text(assistant_msg_content)

        prompt = config.prompt_template.format(
            max_words=config.max_words,
            user_msg=user_msg[:500],
            assistant_msg=assistant_msg[:500],
        )
        return prompt, user_msg

    @staticmethod
    def _normalize_title(raw: str, user_msg: str) -> str:
        """Normalize model output and apply fallback if needed."""
        config = get_title_config()
        title = TitleMiddleware._sanitize_text(raw.strip().strip('"').strip("'"))
        if title and not TitleMiddleware._PLACEHOLDER_TITLE_RE.match(title):
            return title[: config.max_chars] if len(title) > config.max_chars else title
        # Fallback: use first part of user message (by character count)
        fallback_chars = min(config.max_chars, 50)
        if len(user_msg) > fallback_chars:
            return user_msg[:fallback_chars].rstrip() + "..."
        return user_msg if user_msg else "New Conversation"

    def _get_thread_id(self, state: TitleMiddlewareState) -> str | None:
        """Extract thread_id from state for caching."""
        try:
            tid = state.get("thread_id")
            if tid:
                return str(tid)
            runtime_data = state.get("runtime") or {}
            tid = runtime_data.get("thread_id")
            if tid:
                return str(tid)
        except Exception:
            pass
        return None

    async def _generate_title(self, state: TitleMiddlewareState) -> str:
        """Generate a concise title based on the conversation (async path)."""
        config = get_title_config()
        prompt, user_msg = self._build_prompt(state)
        model = create_chat_model(name=config.model_name, thinking_enabled=False)
        try:
            response = await model.ainvoke(prompt)
            title_content = str(response.content) if response.content else ""
            return self._normalize_title(title_content, user_msg)
        except Exception as e:
            print(f"Failed to generate title: {e}")
            return self._normalize_title("", user_msg)

    def _generate_title_sync(self, state: TitleMiddlewareState) -> str:
        """Generate a concise title based on the conversation (sync path)."""
        config = get_title_config()
        prompt, user_msg = self._build_prompt(state)
        model = create_chat_model(name=config.model_name, thinking_enabled=False)
        try:
            response = model.invoke(prompt)
            title_content = str(response.content) if response.content else ""
            return self._normalize_title(title_content, user_msg)
        except Exception as e:
            print(f"Failed to generate title: {e}")
            return self._normalize_title("", user_msg)

    @override
    def after_model(self, state: TitleMiddlewareState, runtime: Runtime) -> dict | None:
        """Generate and set thread title after the first agent response (sync path)."""
        # Skip in flash mode - titles are unnecessary overhead for quick replies
        mode = (runtime.context or {}).get("mode") if runtime.context else None
        if mode == "flash":
            return None

        config = get_title_config()
        if not config.enabled:
            return None

        # Check cache first
        thread_id = self._get_thread_id(state)
        if thread_id:
            with _TITLE_CACHE_LOCK:
                if thread_id in _TITLE_CACHE:
                    return {"title": _TITLE_CACHE[thread_id]}

        # Check if already titled
        if state.get("title"):
            return None

        # Need at least one user+assistant exchange
        messages = state.get("messages", [])
        if len(messages) < 2:
            return None

        user_messages = [m for m in messages if m.type == "human"]
        assistant_messages = [m for m in messages if m.type == "ai"]
        if not (len(user_messages) == 1 and len(assistant_messages) >= 1):
            return None

        # Generate title
        title = self._generate_title_sync(state)

        # Cache it
        if thread_id:
            with _TITLE_CACHE_LOCK:
                _TITLE_CACHE[thread_id] = title

        print(f"Generated thread title: {title}")
        return {"title": title}

    @override
    async def aafter_model(self, state: TitleMiddlewareState, runtime: Runtime) -> dict | None:
        """Generate and set thread title after the first agent response."""
        # Skip in flash mode
        mode = (runtime.context or {}).get("mode") if runtime.context else None
        if mode == "flash":
            return None

        config = get_title_config()
        if not config.enabled:
            return None

        # Check cache first
        thread_id = self._get_thread_id(state)
        if thread_id:
            with _TITLE_CACHE_LOCK:
                if thread_id in _TITLE_CACHE:
                    return {"title": _TITLE_CACHE[thread_id]}

        # Check if already titled
        if state.get("title"):
            return None

        # Need at least one user+assistant exchange
        messages = state.get("messages", [])
        if len(messages) < 2:
            return None

        user_messages = [m for m in messages if m.type == "human"]
        assistant_messages = [m for m in messages if m.type == "ai"]
        if not (len(user_messages) == 1 and len(assistant_messages) >= 1):
            return None

        # Generate title
        title = await self._generate_title(state)

        # Cache it
        if thread_id:
            with _TITLE_CACHE_LOCK:
                _TITLE_CACHE[thread_id] = title

        print(f"Generated thread title: {title}")
        return {"title": title}
