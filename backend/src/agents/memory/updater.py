"""Memory updater for reading, writing, and updating memory data."""

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.agents.memory.prompt import (
    MEMORY_UPDATE_PROMPT,
    format_conversation_for_update,
)
from src.models import create_chat_model
from src.runtime.config.memory_config import get_memory_config
from src.runtime.config.paths import get_paths

logger = logging.getLogger(__name__)


def _get_memory_file_path(agent_name: str | None = None) -> Path:
    """Get the path to the memory file.

    Args:
        agent_name: If provided, returns the per-agent memory file path.
                    If None, returns the global memory file path.

    Returns:
        Path to the memory file.
    """
    if agent_name is not None:
        return get_paths().agent_memory_file(agent_name)

    config = get_memory_config()
    if config.storage_path:
        p = Path(config.storage_path)
        # Absolute path: use as-is; relative path: resolve against base_dir
        return p if p.is_absolute() else get_paths().base_dir / p
    return get_paths().memory_file


def _create_empty_memory() -> dict[str, Any]:
    """Create an empty memory structure."""
    return {
        "version": "1.0",
        "lastUpdated": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "user": {
            "workContext": {"summary": "", "updatedAt": ""},
            "personalContext": {"summary": "", "updatedAt": ""},
            "topOfMind": {"summary": "", "updatedAt": ""},
        },
        "history": {
            "recentMonths": {"summary": "", "updatedAt": ""},
            "earlierContext": {"summary": "", "updatedAt": ""},
            "longTermBackground": {"summary": "", "updatedAt": ""},
        },
        "facts": [],
    }


def _context_section(summary: str = "", updated_at: str = "") -> dict[str, str]:
    return {"summary": summary, "updatedAt": updated_at}


def ensure_memory_schema(memory_data: dict[str, Any] | None) -> dict[str, Any]:
    """Return a writable memory shape while preserving legacy facts."""

    data = dict(memory_data or {})
    empty = _create_empty_memory()
    legacy_context = data.get("user_context")
    legacy_context_text = legacy_context if isinstance(legacy_context, str) else ""

    user = data.get("user")
    if not isinstance(user, dict):
        user = {
            "workContext": _context_section(),
            "personalContext": _context_section(),
            "topOfMind": _context_section(legacy_context_text),
        }
    else:
        user = dict(user)
    for key in ("workContext", "personalContext", "topOfMind"):
        section = user.get(key)
        if not isinstance(section, dict):
            section = {}
        user[key] = _context_section(
            str(section.get("summary") or ""),
            str(section.get("updatedAt") or ""),
        )

    history = data.get("history")
    if not isinstance(history, dict):
        legacy_parts: list[str] = []
        if isinstance(history, list):
            for item in history:
                if isinstance(item, str):
                    legacy_parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("summary") or item.get("content") or ""
                    if text:
                        legacy_parts.append(str(text))
        history = {
            "recentMonths": _context_section("\n".join(legacy_parts).strip()),
            "earlierContext": _context_section(),
            "longTermBackground": _context_section(),
        }
    else:
        history = dict(history)
    for key in ("recentMonths", "earlierContext", "longTermBackground"):
        section = history.get(key)
        if not isinstance(section, dict):
            section = {}
        history[key] = _context_section(
            str(section.get("summary") or ""),
            str(section.get("updatedAt") or ""),
        )

    facts = data.get("facts") if isinstance(data.get("facts"), list) else []
    memory_blocks = data.get("memory_blocks") if isinstance(data.get("memory_blocks"), dict) else {}
    task_phases = data.get("task_phases") if isinstance(data.get("task_phases"), dict) else {}
    return {
        "version": str(data.get("version") or empty["version"]),
        "lastUpdated": str(data.get("lastUpdated") or empty["lastUpdated"]),
        "user": user,
        "history": history,
        "facts": facts,
        "memory_blocks": memory_blocks,
        "task_phases": task_phases,
    }


# Per-agent memory cache: keyed by agent_name (None = global)
# Value: (memory_data, file_mtime)
_memory_cache: dict[str | None, tuple[dict[str, Any], float | None]] = {}


def get_memory_data(agent_name: str | None = None) -> dict[str, Any]:
    """Get the current memory data (cached with file modification time check).

    The cache is automatically invalidated if the memory file has been modified
    since the last load, ensuring fresh data is always returned.

    Args:
        agent_name: If provided, loads per-agent memory. If None, loads global memory.

    Returns:
        The memory data dictionary.
    """
    file_path = _get_memory_file_path(agent_name)

    # Get current file modification time
    try:
        current_mtime = file_path.stat().st_mtime if file_path.exists() else None
    except OSError:
        current_mtime = None

    cached = _memory_cache.get(agent_name)

    # Invalidate cache if file has been modified or doesn't exist
    if cached is None or cached[1] != current_mtime:
        memory_data = _load_memory_from_file(agent_name)
        _memory_cache[agent_name] = (memory_data, current_mtime)
        return memory_data

    return cached[0]


def reload_memory_data(agent_name: str | None = None) -> dict[str, Any]:
    """Reload memory data from file, forcing cache invalidation.

    Args:
        agent_name: If provided, reloads per-agent memory. If None, reloads global memory.

    Returns:
        The reloaded memory data dictionary.
    """
    file_path = _get_memory_file_path(agent_name)
    memory_data = _load_memory_from_file(agent_name)

    try:
        mtime = file_path.stat().st_mtime if file_path.exists() else None
    except OSError:
        mtime = None

    _memory_cache[agent_name] = (memory_data, mtime)
    return memory_data


def _load_memory_from_file(agent_name: str | None = None) -> dict[str, Any]:
    """Load memory data from file.

    Args:
        agent_name: If provided, loads per-agent memory file. If None, loads global.

    Returns:
        The memory data dictionary.
    """
    file_path = _get_memory_file_path(agent_name)

    if not file_path.exists():
        return _create_empty_memory()

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load memory file: %s", e)
        return _create_empty_memory()


# Matches sentences that describe a file-upload *event* rather than general
# file-related work.  Deliberately narrow to avoid removing legitimate facts
# such as "User works with CSV files" or "prefers PDF export".
_UPLOAD_SENTENCE_RE = re.compile(
    r"[^.!?]*\b(?:"
    r"upload(?:ed|ing)?(?:\s+\w+){0,3}\s+(?:file|files?|document|documents?|attachment|attachments?)"
    r"|file\s+upload"
    r"|/mnt/user-data/uploads/"
    r"|<uploaded_files>"
    r")[^.!?]*[.!?]?\s*",
    re.IGNORECASE,
)


def _strip_upload_mentions_from_memory(memory_data: dict[str, Any]) -> dict[str, Any]:
    """Remove sentences about file uploads from all memory summaries and facts.

    Uploaded files are session-scoped; persisting upload events in long-term
    memory causes the agent to search for non-existent files in future sessions.
    """
    # Scrub summaries in user/history sections
    for section in ("user", "history"):
        section_data = memory_data.get(section, {})
        if not isinstance(section_data, dict):
            continue
        for _key, val in section_data.items():
            if isinstance(val, dict) and "summary" in val:
                cleaned = _UPLOAD_SENTENCE_RE.sub("", val["summary"]).strip()
                cleaned = re.sub(r"  +", " ", cleaned)
                val["summary"] = cleaned

    # Also remove any facts that describe upload events
    facts = memory_data.get("facts", [])
    if facts:
        memory_data["facts"] = [f for f in facts if not _UPLOAD_SENTENCE_RE.search(f.get("content", ""))]

    return memory_data


def _normalise_completed_item(value: Any) -> str:
    """Return stable text for a completed task item."""
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _completed_item_hash(value: Any) -> str:
    """Hash completed work so compaction resumes can de-duplicate it."""
    normalised = _normalise_completed_item(value)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16] if normalised else ""


def _metadata_list(metadata: dict[str, Any], key: str) -> list[str]:
    raw = metadata.get(key)
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _task_phase_id(thread_id: str | None, metadata: dict[str, Any]) -> str:
    value = metadata.get("task_phase_id") or metadata.get("context_cycle_id")
    if value:
        return str(value)
    return f"thread:{thread_id or 'unknown'}"


def _source_event_id(thread_id: str | None, metadata: dict[str, Any], now: str) -> str:
    value = metadata.get("source_event_id")
    if value:
        return str(value)
    trigger = metadata.get("compaction_trigger") or metadata.get("memory_scope") or "conversation"
    basis = f"{thread_id or 'unknown'}:{_task_phase_id(thread_id, metadata)}:{trigger}:{now}"
    return f"event_{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"


def _ensure_task_phase(memory_data: dict[str, Any], *, task_phase_id: str, source_event_id: str, now: str) -> dict[str, Any]:
    phases = memory_data.setdefault("task_phases", {})
    if not isinstance(phases, dict):
        phases = {}
        memory_data["task_phases"] = phases
    phase = phases.setdefault(
        task_phase_id,
        {
            "id": task_phase_id,
            "createdAt": now,
            "updatedAt": now,
            "sourceEventIds": [],
            "completedItemHashes": [],
        },
    )
    phase["updatedAt"] = now
    events = phase.setdefault("sourceEventIds", [])
    if source_event_id not in events:
        events.append(source_event_id)
    return phase


def _known_completed_hashes(memory_data: dict[str, Any], task_phase_id: str) -> set[str]:
    hashes: set[str] = set()
    phase = memory_data.get("task_phases", {}).get(task_phase_id, {}) if isinstance(memory_data.get("task_phases"), dict) else {}
    if isinstance(phase, dict):
        hashes.update(str(item) for item in phase.get("completedItemHashes", []) if item)
    for fact in memory_data.get("facts", []):
        if isinstance(fact, dict) and fact.get("taskPhaseId") == task_phase_id and fact.get("completedItemHash"):
            hashes.add(str(fact["completedItemHash"]))
    return hashes


def _save_memory_to_file(memory_data: dict[str, Any], agent_name: str | None = None) -> bool:
    """Save memory data to file and update cache.

    Args:
        memory_data: The memory data to save.
        agent_name: If provided, saves to per-agent memory file. If None, saves to global.

    Returns:
        True if successful, False otherwise.
    """
    file_path = _get_memory_file_path(agent_name)

    try:
        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Update lastUpdated timestamp
        memory_data["lastUpdated"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # Write atomically using temp file
        temp_path = file_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(memory_data, f, indent=2, ensure_ascii=False)

        # Rename temp file to actual file (atomic on most systems)
        temp_path.replace(file_path)

        # Update cache and file modification time
        try:
            mtime = file_path.stat().st_mtime
        except OSError:
            mtime = None

        _memory_cache[agent_name] = (memory_data, mtime)

        logger.debug("Memory saved to %s", file_path)
        return True
    except OSError as e:
        logger.warning("Failed to save memory file: %s", e)
        return False


class MemoryUpdater:
    """Updates memory using LLM based on conversation context."""

    def __init__(self, model_name: str | None = None):
        """Initialize the memory updater.

        Args:
            model_name: Optional model name to use. If None, uses config or default.
        """
        self._model_name = model_name

    def _get_model(self):
        """Get the model for memory updates."""
        config = get_memory_config()
        model_name = self._model_name or config.model_name
        return create_chat_model(name=model_name, thinking_enabled=False)

    async def update_memory(
        self,
        messages: list[Any],
        thread_id: str | None = None,
        agent_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Update memory based on conversation messages.

        Args:
            messages: List of conversation messages.
            thread_id: Optional thread ID for tracking source.
            agent_name: If provided, updates per-agent memory. If None, updates global memory.

        Returns:
            True if update was successful, False otherwise.
        """
        config = get_memory_config()
        if not config.enabled:
            return False

        if not messages:
            return False

        try:
            # Get current memory
            current_memory = ensure_memory_schema(get_memory_data(agent_name))

            # Format conversation for prompt
            conversation_text = format_conversation_for_update(messages)

            if not conversation_text.strip():
                return False

            # Build prompt
            prompt = MEMORY_UPDATE_PROMPT.format(
                current_memory=json.dumps(current_memory, indent=2),
                conversation=conversation_text,
            )

            # Call LLM
            model = self._get_model()
            response = await model.ainvoke(prompt)
            response_text = str(response.content).strip()

            # Parse response
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            update_data = json.loads(response_text)

            # Apply updates
            updated_memory = self._apply_updates(current_memory, update_data, thread_id, metadata=metadata)

            # Strip file-upload mentions from all summaries before saving.
            # Uploaded files are session-scoped and won't exist in future sessions,
            # so recording upload events in long-term memory causes the agent to
            # try (and fail) to locate those files in subsequent conversations.
            updated_memory = _strip_upload_mentions_from_memory(updated_memory)

            # Save
            return _save_memory_to_file(updated_memory, agent_name)

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM response for memory update: %s", e)
            return False
        except Exception as e:
            logger.warning("Memory update failed: %s", e)
            return False

    def _apply_updates(
        self,
        current_memory: dict[str, Any],
        update_data: dict[str, Any],
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply LLM-generated updates to memory.

        Args:
            current_memory: Current memory data.
            update_data: Updates from LLM.
            thread_id: Optional thread ID for tracking.

        Returns:
            Updated memory data.
        """
        current_memory = ensure_memory_schema(current_memory)
        config = get_memory_config()
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        source_metadata = dict(metadata or {})
        task_phase_id = _task_phase_id(thread_id, source_metadata)
        source_event_id = _source_event_id(thread_id, source_metadata, now)
        completed_hashes = _metadata_list(source_metadata, "completed_item_hashes")
        if not completed_hashes and source_metadata.get("completed_item_hash"):
            completed_hashes = [str(source_metadata["completed_item_hash"])]
        source_metadata.update(
            {
                "task_phase_id": task_phase_id,
                "source_event_id": source_event_id,
            }
        )
        if completed_hashes:
            source_metadata["completed_item_hashes"] = completed_hashes
        phase = _ensure_task_phase(
            current_memory,
            task_phase_id=task_phase_id,
            source_event_id=source_event_id,
            now=now,
        )
        known_hashes = _known_completed_hashes(current_memory, task_phase_id)

        # Update user sections
        updated_summary = False
        user_updates = update_data.get("user", {})
        for section in ["workContext", "personalContext", "topOfMind"]:
            section_data = user_updates.get(section, {})
            if section_data.get("shouldUpdate") and section_data.get("summary"):
                current_memory["user"][section] = {
                    "summary": section_data["summary"],
                    "updatedAt": now,
                }
                updated_summary = True

        # Update history sections
        history_updates = update_data.get("history", {})
        for section in ["recentMonths", "earlierContext", "longTermBackground"]:
            section_data = history_updates.get(section, {})
            if section_data.get("shouldUpdate") and section_data.get("summary"):
                current_memory["history"][section] = {
                    "summary": section_data["summary"],
                    "updatedAt": now,
                }
                updated_summary = True

        # Remove facts
        facts_to_remove = set(update_data.get("factsToRemove", []))
        if facts_to_remove:
            current_memory["facts"] = [f for f in current_memory.get("facts", []) if f.get("id") not in facts_to_remove]

        # Add new facts
        new_facts = update_data.get("newFacts", [])
        facts_added: list[dict[str, Any]] = []
        for fact in new_facts:
            confidence = fact.get("confidence", 0.5)
            if confidence >= config.fact_confidence_threshold:
                content = str(fact.get("content") or "").strip()
                fact_completed_hash = str(fact.get("completed_item_hash") or fact.get("completedItemHash") or "").strip()
                if not fact_completed_hash and completed_hashes and len(completed_hashes) == 1:
                    fact_completed_hash = completed_hashes[0]
                if not fact_completed_hash and source_metadata.get("compaction_trigger") and content:
                    fact_completed_hash = _completed_item_hash(content)
                if fact_completed_hash and fact_completed_hash in known_hashes:
                    logger.debug(
                        "Skipping duplicate memory fact for task phase %s completed hash %s",
                        task_phase_id,
                        fact_completed_hash,
                    )
                    continue
                fact_entry = {
                    "id": f"fact_{uuid.uuid4().hex[:8]}",
                    "content": content,
                    "category": fact.get("category", "context"),
                    "confidence": confidence,
                    "createdAt": now,
                    "source": thread_id or "unknown",
                    "sourceMetadata": dict(source_metadata),
                    "taskPhaseId": task_phase_id,
                    "sourceEventId": source_event_id,
                }
                if fact_completed_hash:
                    fact_entry["completedItemHash"] = fact_completed_hash
                    known_hashes.add(fact_completed_hash)
                    phase_hashes = phase.setdefault("completedItemHashes", [])
                    if fact_completed_hash not in phase_hashes:
                        phase_hashes.append(fact_completed_hash)
                current_memory["facts"].append(fact_entry)
                facts_added.append(fact_entry)

        for completed_hash in completed_hashes:
            if completed_hash and completed_hash not in phase.setdefault("completedItemHashes", []):
                phase["completedItemHashes"].append(completed_hash)

        if facts_added and not updated_summary:
            self._backfill_summary_from_facts(current_memory, facts_added, now)

        # Enforce max facts limit
        if len(current_memory["facts"]) > config.max_facts:
            # Sort by confidence and keep top ones
            current_memory["facts"] = sorted(
                current_memory["facts"],
                key=lambda f: f.get("confidence", 0),
                reverse=True,
            )[: config.max_facts]

        return current_memory

    @staticmethod
    def _backfill_summary_from_facts(
        current_memory: dict[str, Any],
        new_facts: list[dict[str, Any]],
        now: str,
    ) -> None:
        fact_texts = [str(fact.get("content") or "").strip() for fact in new_facts if str(fact.get("content") or "").strip()]
        if not fact_texts:
            return
        summary = "; ".join(fact_texts[:4])[:700]
        top_of_mind = current_memory.setdefault("user", {}).setdefault(
            "topOfMind",
            {"summary": "", "updatedAt": ""},
        )
        if not str(top_of_mind.get("summary") or "").strip():
            top_of_mind["summary"] = summary
            top_of_mind["updatedAt"] = now
        recent = current_memory.setdefault("history", {}).setdefault(
            "recentMonths",
            {"summary": "", "updatedAt": ""},
        )
        if not str(recent.get("summary") or "").strip():
            recent["summary"] = summary
            recent["updatedAt"] = now


async def update_memory_from_conversation(
    messages: list[Any],
    thread_id: str | None = None,
    agent_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Convenience function to update memory from a conversation.

    Args:
        messages: List of conversation messages.
        thread_id: Optional thread ID.
        agent_name: If provided, updates per-agent memory. If None, updates global memory.

    Returns:
        True if successful, False otherwise.
    """
    updater = MemoryUpdater()
    return await updater.update_memory(messages, thread_id, agent_name, metadata=metadata)
