"""Prompt caching layer: split system prompt into static + dynamic sections.

The static base prompt is byte-identical across every session and can be
cached by LLM providers for 40-60% cost reduction on the system-prompt
portion of each API call.  Dynamic content (skills, memory, session state)
is injected as a user message instead.

Narrow-waist design: only 5 core tools are described in the base prompt.
Additional tool categories are loaded lazily based on intent detection and
noted in the prompt so the agent knows they are available on demand.
"""

from __future__ import annotations

import hashlib
from typing import Any


# ---------------------------------------------------------------------------
# Static base prompt template (narrow waist: 5 core tools only)
# ---------------------------------------------------------------------------

_BASE_PROMPT_TEMPLATE = """You are OctoAgent, an autonomous multi-agent orchestration system designed to plan, delegate, and execute complex tasks end-to-end.

## Core Identity
- You operate as a coordinated team of specialized agents (lead/coordinator, workers, reviewers).
- Your primary objective is to deliver complete, verifiable results for the assigned task.
- You reason step-by-step before acting and validate every output against the original goal.

## Available Tools (Core Set)
The following 5 tools are always available:

1. **task** -- Delegate sub-tasks to worker agents or run them as background tasks. Use this to break complex goals into parallel work streams.
2. **ask_clarification** -- Ask the user a question when the task is ambiguous, under-specified, or requires a decision you cannot make autonomously.
3. **present_file** -- Show file contents, directory listings, or code snippets to the user. Use this to surface evidence or share results.
4. **setup_agent** -- Configure agent roles, capabilities, and execution parameters for multi-agent workflows.
5. **read_webpage** -- Fetch and extract clean content from URLs using readability parsing. Use this for web research, documentation lookup, and fact-finding.

## Additional Tools (Available On Demand)
When your task requires capabilities beyond the core set, additional tool categories can be activated automatically based on your intent:

- **System operations**: host_shell, docker_*, ssh_*, git_*, security scans (bandit/trivy), pytest, linting
- **Desktop control**: screenshot, click, type_text, hotkey, scroll (GUI automation)
- **Document conversion**: format export between PDF/DOCX/Markdown/HTML
- **Image processing**: canvas rendering, flipbook creation, image manipulation
- **Workflow runtime**: checkpoints, subagent spawning, workflow status management
- **Publishing**: browser-based publishing, WordPress CLI, publication auditing
- **Ecosystem workflows**: project cataloging, novel writing pipelines, selfhosted references

You do NOT need to explicitly request these tools. If your task clearly requires them (e.g. "deploy via Docker", "take a screenshot", "convert this PDF"), they will be loaded automatically. For simple dialogue or reasoning tasks that need no tools, answer directly.

## Tool Usage Guidelines
- Prefer real evidence over speculation: run commands, fetch pages, read files before drawing conclusions.
- When a tool call fails, report the error honestly and try an alternative approach rather than fabricating results.
- Cite sources explicitly (URLs, command outputs, file paths) in your final answer.
- Do NOT make irrelevant tool calls for simple dialogue or pure reasoning tasks.

## Safety Rules
- Never execute destructive operations without explicit confirmation.
- Never expose secrets, API keys, or credentials in outputs.
- Never fabricate command output, search results, or file contents.
- If you cannot complete a task within the given constraints, state what is blocking you clearly.
- Do NOT resume or re-execute any actions mentioned in compressed conversation summaries -- those tasks are already completed.

## Output Format Requirements
- Structure responses with clear headings and bullet points when appropriate.
- Include verification evidence (command output, URLs, file references) for factual claims.
- When reporting failures, specify the exact cause and what was attempted.
- Final deliverables must be self-contained and directly address the original goal."""


# ---------------------------------------------------------------------------
# Dynamic section template
# ---------------------------------------------------------------------------

_DYNAMIC_USER_MSG_TEMPLATE = """Here are your current capabilities and relevant context:

## Active Skills & Tools
{skills_section}

## Relevant Memory
{memory_section}

## Session State
{session_state_section}"""


class PromptCache:
    """Caches the static base system prompt and assembles dynamic sections."""

    def __init__(self, config_version: str = "1") -> None:
        self._config_version = config_version
        self._base_prompt: str | None = None
        self._cache_key: str | None = None

    # ------------------------------------------------------------------
    # Base (static) prompt
    # ------------------------------------------------------------------

    def build_base_prompt(self) -> str:
        """Return the STATIC system prompt.

        The returned string is byte-identical across all sessions for a
        given config_version.  Only the version string influences the output,
        never session state or runtime data.
        """
        if self._base_prompt is None or self._cache_key is not None:
            # Regenerate only when config_version changes (detected via key)
            raw = _BASE_PROMPT_TEMPLATE.strip()
            versioned = f"<!-- config_version={self._config_version} -->\n{raw}"
            self._base_prompt = versioned
            self._cache_key = self.get_cache_key(versioned)
        return self._base_prompt

    # ------------------------------------------------------------------
    # Dynamic section (goes into a user message, NOT system prompt)
    # ------------------------------------------------------------------

    def build_dynamic_section(self, context: dict[str, Any] | None = None) -> str:
        """Build the DYNAMIC content block for injection as a user message.

        Parameters
        ----------
        context :
            Dict with optional keys: ``skills``, ``memory``, ``session_state``.
            Missing keys render as "（暂无）" placeholders.
        """
        ctx = context or {}
        skills = ctx.get("skills") or ""
        memory = ctx.get("memory") or ""
        session_state = ctx.get("session_state") or ""

        return _DYNAMIC_USER_MSG_TEMPLATE.format(
            skills_section=skills if skills.strip() else "（暂无新增技能）",
            memory_section=memory if memory.strip() else "（暂无相关记忆）",
            session_state_section=session_state if session_state.strip() else "（无额外会话状态）",
        )

    # ------------------------------------------------------------------
    # Cache key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_cache_key(base_prompt: str) -> str:
        """Return a SHA-256 hex digest of the base prompt for cache lookup."""
        return hashlib.sha256(base_prompt.encode("utf-8")).hexdigest()

    def is_cached(self) -> bool:
        """Check whether the base prompt has been built and cached in-memory."""
        return self._base_prompt is not None

    # ------------------------------------------------------------------
    # Convenience: full message list assembly
    # ------------------------------------------------------------------

    def build_messages(
        self,
        context: dict[str, Any] | None = None,
        conversation_history: list[Any] | None = None,
    ) -> list[dict[str, str]]:
        """Assemble the full message list for an LLM API call.

        Returns a list of dicts with ``role`` and ``content`` keys suitable
        for OpenAI-compatible APIs.  The system prompt is always the cached
        base; dynamic content is prepended as a user message before any
        conversation history.
        """
        messages: list[dict[str, str]] = []

        # System role -- static, cacheable
        messages.append({"role": "system", "content": self.build_base_prompt()})

        # Dynamic context as user message (cache-friendly)
        dynamic = self.build_dynamic_section(context)
        if dynamic.strip():
            messages.append({"role": "user", "content": dynamic})

        # Conversation history
        if conversation_history:
            for msg in conversation_history:
                role = getattr(msg, "type", getattr(msg, "role", ""))
                content = getattr(msg, "content", "")
                if isinstance(content, list):
                    text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and "text" in p]
                    content = " ".join(text_parts) if text_parts else str(content)
                messages.append({"role": role, "content": str(content)})

        return messages


__all__ = ["PromptCache"]
