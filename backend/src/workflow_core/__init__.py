from .contracts import (
    AgentConversationRef,
    AgentHandle,
    AgentMessage,
    CheckpointRef,
    CreateAgentMessageRequest,
    CreateCheckpointRequest,
    CreateTaskWorkspaceRequest,
    DeploymentInterface,
    DockerExecutionProfile,
    TaskCard,
    TaskCardEdge,
    TaskCardGraph,
    TaskExecutionMode,
    TaskProgress,
    TaskWorkspace,
    TaskWorkspaceStatus,
    TaskWorkspaceSummary,
    UpdateTaskCardGraphRequest,
    UpdateTaskWorkspaceRequest,
    make_id,
    utc_now,
)
from .runtime_contracts import (
    TaskArtifactFile,
    TaskStudioAgentSummary,
    TaskStudioBindingItem,
    TaskStudioBindings,
    TaskStudioChannelBinding,
    TaskStudioCheckpointSummary,
    TaskStudioHandoff,
    TaskStudioReadiness,
    TaskStudioRuntimeEventsResponse,
    TaskStudioRuntimeResponse,
    TaskStudioRuntimeSummary,
    TaskStudioTimelineEvent,
    TaskStudioWorkflowSummary,
)

__all__ = [
    "AgentConversationRef",
    "AgentHandle",
    "AgentMessage",
    "CheckpointRef",
    "CreateAgentMessageRequest",
    "CreateCheckpointRequest",
    "CreateTaskWorkspaceRequest",
    "DeploymentInterface",
    "DockerExecutionProfile",
    "execute_agent_message",
    "TaskCard",
    "TaskCardEdge",
    "TaskCardGraph",
    "TaskArtifactFile",
    "TaskExecutionMode",
    "TaskProgress",
    "TaskStudioAgentSummary",
    "TaskStudioBindingItem",
    "TaskStudioBindings",
    "TaskStudioChannelBinding",
    "TaskStudioCheckpointSummary",
    "TaskStudioHandoff",
    "TaskStudioReadiness",
    "TaskStudioRuntimeEventsResponse",
    "TaskStudioRuntimeResponse",
    "TaskStudioRuntimeSummary",
    "TaskStudioTimelineEvent",
    "TaskStudioWorkflowSummary",
    "TaskWorkflowModule",
    "TaskWorkspace",
    "TaskWorkspaceStatus",
    "TaskWorkspaceSummary",
    "UpdateTaskCardGraphRequest",
    "UpdateTaskWorkspaceRequest",
    "WorkflowCoreService",
    "WorkflowFileManager",
    "WorkflowProjectionFacade",
    "has_agent_messages",
    "get_workflow_core_service",
    "get_workflow_execution_controller",
    "get_workflow_message_executor",
    "invoke_langgraph_assistant",
    "recoverable_orphaned_workspaces",
    "safe_auto_execute_lead_agent",
    "safe_auto_execute_workspace",
    "make_id",
    "utc_now",
]


def __getattr__(name: str):
    if name == "WorkflowFileManager":
        from .files import WorkflowFileManager

        return WorkflowFileManager
    if name == "WorkflowProjectionFacade":
        from .projection import WorkflowProjectionFacade

        return WorkflowProjectionFacade
    if name in {
        "TaskWorkflowModule",
        "WorkflowCoreService",
        "get_workflow_core_service",
        "get_workflow_execution_controller",
        "get_workflow_message_executor",
    }:
        from .service import (
            TaskWorkflowModule,
            WorkflowCoreService,
            get_workflow_core_service,
            get_workflow_execution_controller,
            get_workflow_message_executor,
        )

        return {
            "TaskWorkflowModule": TaskWorkflowModule,
            "WorkflowCoreService": WorkflowCoreService,
            "get_workflow_core_service": get_workflow_core_service,
            "get_workflow_execution_controller": get_workflow_execution_controller,
            "get_workflow_message_executor": get_workflow_message_executor,
        }[name]
    if name in {
        "execute_agent_message",
        "has_agent_messages",
        "invoke_langgraph_assistant",
        "recoverable_orphaned_workspaces",
        "safe_auto_execute_lead_agent",
        "safe_auto_execute_workspace",
    }:
        from .runtime import (
            execute_agent_message,
            has_agent_messages,
            invoke_langgraph_assistant,
            recoverable_orphaned_workspaces,
            safe_auto_execute_lead_agent,
            safe_auto_execute_workspace,
        )

        return {
            "execute_agent_message": execute_agent_message,
            "has_agent_messages": has_agent_messages,
            "invoke_langgraph_assistant": invoke_langgraph_assistant,
            "recoverable_orphaned_workspaces": recoverable_orphaned_workspaces,
            "safe_auto_execute_lead_agent": safe_auto_execute_lead_agent,
            "safe_auto_execute_workspace": safe_auto_execute_workspace,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")