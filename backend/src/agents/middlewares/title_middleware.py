"""Middleware for automatic thread title generation."""

import html
import re
from typing import NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from src.models import create_chat_model
from src.runtime.config.title_config import get_title_config


class TitleMiddlewareState(AgentState):
    """Compatible with the `ThreadState` schema."""

    title: NotRequired[str | None]


class TitleMiddleware(AgentMiddleware[TitleMiddlewareState]):
    """Automatically generate a title for the thread after the first user message."""

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

    def _should_generate_title(self, state: TitleMiddlewareState) -> bool:
        """Check if we should generate a title for this thread."""
        config = get_title_config()
        if not config.enabled:
            return False

        # Check if thread already has a title in state
        if state.get("title"):
            return False

        # Check if this is the first turn (has at least one user message and one assistant response)
        messages = state.get("messages", [])
        if len(messages) < 2:
            return False

        # Count user and assistant messages
        user_messages = [m for m in messages if m.type == "human"]
        assistant_messages = [m for m in messages if m.type == "ai"]

        # Generate title after first complete exchange
        return len(user_messages) == 1 and len(assistant_messages) >= 1

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
        if self._should_generate_title(state):
            title = self._generate_title_sync(state)
            print(f"Generated thread title: {title}")
            return {"title": title}
        return None

    @override
    async def aafter_model(self, state: TitleMiddlewareState, runtime: Runtime) -> dict | None:
        """Generate and set thread title after the first agent response."""
        if self._should_generate_title(state):
            title = await self._generate_title(state)
            print(f"Generated thread title: {title}")

            # Store title in state (will be persisted by checkpointer if configured)
            return {"title": title}

        return None
