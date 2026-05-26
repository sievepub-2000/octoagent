from typing import Any

from pydantic import BaseModel, Field

from src.storage.brain import BrainBuilderActionModel
from src.storage.query import QuerySession
from src.storage.workflow import (
    AgentHandle,
    AgentMessage,
    TaskArtifactFile,
    TaskCardGraph,
    TaskProgress,
    TaskStudioRuntimeEventsResponse,
    TaskStudioRuntimeResponse,
    TaskWorkspace,
    TaskWorkspaceSummary,
)


class TaskWorkspaceListResponse(BaseModel):
    workspaces: list[TaskWorkspaceSummary] = Field(default_factory=list)


class TaskCardGraphResponse(BaseModel):
    task_id: str
    card_graph: TaskCardGraph
    progress: TaskProgress


class TaskAgentListResponse(BaseModel):
    task_id: str
    agents: list[AgentHandle] = Field(default_factory=list)


class TaskAgentMessagesResponse(BaseModel):
    task_id: str
    agent_id: str
    messages: list[AgentMessage] = Field(default_factory=list)


class TaskRunLogResponse(BaseModel):
    task_id: str
    run_log: str


class TaskResultResponse(BaseModel):
    task_id: str
    result_content: str
    has_result: bool = True
    source_path: str | None = None
    source_label: str | None = None
    available_sources: list[str] = Field(default_factory=list)


class TaskArtifactListResponse(BaseModel):
    task_id: str
    files: list[TaskArtifactFile] = Field(default_factory=list)


class TaskWorkspaceBuilderHistoryEntry(BaseModel):
    transaction_id: str
    revision: int
    applied_at: str
    action_ids: list[str] = Field(default_factory=list)
    action_title: str
    patch: dict[str, Any] = Field(default_factory=dict)


class TaskWorkspaceBuilderPreviewResponse(BaseModel):
    task_id: str
    generated_at: str
    summary: str
    builder_action_model: BrainBuilderActionModel
    current_draft: dict[str, Any] = Field(default_factory=dict)
    revision: int = 0
    applied_action_ids: list[str] = Field(default_factory=list)
    history: list[TaskWorkspaceBuilderHistoryEntry] = Field(default_factory=list)


class TaskWorkspaceBuilderHistoryResponse(BaseModel):
    task_id: str
    revision: int = 0
    current_draft: dict[str, Any] = Field(default_factory=dict)
    applied_action_ids: list[str] = Field(default_factory=list)
    history: list[TaskWorkspaceBuilderHistoryEntry] = Field(default_factory=list)


class ApplyTaskWorkspaceBuilderActionRequest(BaseModel):
    action_id: str


class ApplyTaskWorkspaceBuilderBatchRequest(BaseModel):
    action_ids: list[str] = Field(default_factory=list)
    use_apply_all_patch: bool = False


class ExecuteTaskRequest(BaseModel):
    auto_compile: bool = True
    auto_iterate: bool = False
    max_iterations: int = 1


def build_task_workspace_builder_history_response(history: Any) -> TaskWorkspaceBuilderHistoryResponse:
    return TaskWorkspaceBuilderHistoryResponse(
        task_id=history.task_id,
        revision=history.revision,
        current_draft=history.current_draft,
        applied_action_ids=history.applied_action_ids,
        history=[
            TaskWorkspaceBuilderHistoryEntry(
                transaction_id=entry.transaction_id,
                revision=entry.revision,
                applied_at=entry.applied_at,
                action_ids=entry.action_ids,
                action_title=entry.action_title,
                patch=entry.patch,
            )
            for entry in history.history
        ],
    )


def build_task_workspace_builder_preview_response(preview: Any) -> TaskWorkspaceBuilderPreviewResponse:
    return TaskWorkspaceBuilderPreviewResponse(
        task_id=preview.task_id,
        generated_at=preview.generated_at,
        summary=preview.summary,
        builder_action_model=preview.builder_action_model,
        current_draft=preview.current_draft,
        revision=preview.revision,
        applied_action_ids=preview.applied_action_ids,
        history=[
            TaskWorkspaceBuilderHistoryEntry(
                transaction_id=entry.transaction_id,
                revision=entry.revision,
                applied_at=entry.applied_at,
                action_ids=entry.action_ids,
                action_title=entry.action_title,
                patch=entry.patch,
            )
            for entry in preview.history
        ],
    )


__all__ = [
    "ApplyTaskWorkspaceBuilderActionRequest",
    "ApplyTaskWorkspaceBuilderBatchRequest",
    "ExecuteTaskRequest",
    "QuerySession",
    "TaskAgentListResponse",
    "TaskAgentMessagesResponse",
    "TaskArtifactListResponse",
    "TaskCardGraphResponse",
    "TaskResultResponse",
    "TaskRunLogResponse",
    "TaskStudioRuntimeEventsResponse",
    "TaskStudioRuntimeResponse",
    "TaskWorkspace",
    "TaskWorkspaceBuilderHistoryResponse",
    "TaskWorkspaceBuilderPreviewResponse",
    "TaskWorkspaceListResponse",
    "build_task_workspace_builder_history_response",
    "build_task_workspace_builder_preview_response",
]
