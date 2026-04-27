from typing import Annotated, NotRequired, TypedDict

from langchain.agents import AgentState


class SandboxState(TypedDict):
    sandbox_id: NotRequired[str | None]


class ThreadDataState(TypedDict):
    workspace_path: NotRequired[str | None]
    uploads_path: NotRequired[str | None]
    outputs_path: NotRequired[str | None]


class ViewedImageData(TypedDict):
    base64: str
    mime_type: str


class ThreadContinuationState(TypedDict):
    source_thread_id: str
    trigger: str
    source_title: NotRequired[str | None]
    message_count: NotRequired[int | None]
    workflow_count: NotRequired[int | None]
    continued_at: NotRequired[str | None]


class ThreadRuntimeState(TypedDict):
    primary_model: NotRequired[str | None]
    fallback_chain: NotRequired[list[str] | None]
    fallback_ready: NotRequired[bool | None]
    embedded_backup_enabled: NotRequired[bool | None]
    continuation_source: NotRequired[str | None]
    continuation_mode: NotRequired[str | None]
    workflow_resume_state: NotRequired[str | None]
    memory_guard_state: NotRequired[str | None]
    context_pressure: NotRequired[str | None]
    recommended_memory_action: NotRequired[str | None]
    goal_drift_status: NotRequired[str | None]
    client_command_target: NotRequired[str | None]
    planned_operation_id: NotRequired[str | None]
    updated_at: NotRequired[str | None]


def merge_artifacts(existing: list[str] | None, new: list[str] | None) -> list[str]:
    """Reducer for artifacts list - merges and deduplicates artifacts."""
    if existing is None:
        return new or []
    if new is None:
        return existing
    # Use dict.fromkeys to deduplicate while preserving order
    return list(dict.fromkeys(existing + new))


def merge_viewed_images(existing: dict[str, ViewedImageData] | None, new: dict[str, ViewedImageData] | None) -> dict[str, ViewedImageData]:
    """Reducer for viewed_images dict - merges image dictionaries.

    Special case: If new is an empty dict {}, it clears the existing images.
    This allows middlewares to clear the viewed_images state after processing.
    """
    if existing is None:
        return new or {}
    if new is None:
        return existing
    # Special case: empty dict means clear all viewed images
    if len(new) == 0:
        return {}
    # Merge dictionaries, new values override existing ones for same keys
    return {**existing, **new}


class ThreadState(AgentState):
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]
    continuation: NotRequired[ThreadContinuationState | None]
    runtime: NotRequired[ThreadRuntimeState | None]
    title: NotRequired[str | None]
    artifacts: Annotated[list[str], merge_artifacts]
    todos: NotRequired[list | None]
    workflows: NotRequired[list[dict] | None]
    workflow_events: NotRequired[list[dict] | None]
    uploaded_files: NotRequired[list[dict] | None]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]  # image_path -> {base64, mime_type}
