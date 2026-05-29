"""Builder action transaction layer for Slice D.

Owns preview, apply, batch-apply, and history for Brain builder actions.
Keeps Brain as a recommendation producer; WorkflowCore owns patch validation
and persistence through controlled update paths.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from src.storage.brain.contracts import BrainBuilderActionModel, BrainTaskContext
from src.storage.brain.service import BrainCoreService
from src.storage.task_workspaces.contracts import TaskWorkspace
from src.utils.datetime import utc_now_iso as _utc_now

# ---------------------------------------------------------------------------
# Transaction data structures
# ---------------------------------------------------------------------------


class BuilderHistoryEntry(BaseModel):
    transaction_id: str
    revision: int
    applied_at: str
    action_ids: list[str]
    action_title: str
    patch: dict[str, Any] = Field(default_factory=dict)
    source: str = "brain"
    applied_by: str = "operator"


class BuilderPreviewResponse(BaseModel):
    task_id: str
    generated_at: str
    summary: str
    builder_action_model: BrainBuilderActionModel
    current_draft: dict[str, Any] = Field(default_factory=dict)
    revision: int = 0
    applied_action_ids: list[str] = Field(default_factory=list)
    history: list[BuilderHistoryEntry] = Field(default_factory=list)
    conflict_warnings: list[str] = Field(default_factory=list)


class BuilderApplyResponse(BaseModel):
    task_id: str
    transaction_id: str
    status: str = "applied"
    revision: int
    current_draft: dict[str, Any] = Field(default_factory=dict)
    applied_action_ids: list[str] = Field(default_factory=list)
    history: list[BuilderHistoryEntry] = Field(default_factory=list)
    affected_keys: list[str] = Field(default_factory=list)


class BuilderHistoryResponse(BaseModel):
    task_id: str
    revision: int = 0
    current_draft: dict[str, Any] = Field(default_factory=dict)
    applied_action_ids: list[str] = Field(default_factory=list)
    history: list[BuilderHistoryEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------




def _metadata_string(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _preferred_brain_mode(workspace_mode: str) -> str:
    mapping = {
        "single": "plan",
        "branch": "plan",
        "group": "plan",
        "quant": "quant",
        "research": "research",
        "policy": "policy",
    }
    return mapping.get(workspace_mode, "plan")


def _workflow_mode_for_workspace(mode: str) -> str:
    return {"single": "task", "branch": "branch", "group": "group"}.get(mode, "task")


def deep_merge_patch(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge *right* into *left*, returning a new dict."""
    merged = dict(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_patch(merged[key], value)
        else:
            merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# State extraction
# ---------------------------------------------------------------------------


def extract_builder_state(metadata: dict[str, object]) -> dict[str, Any]:
    raw = metadata.get("brain_builder_state")
    return dict(raw) if isinstance(raw, dict) else {}


def extract_builder_draft(state: dict[str, Any]) -> dict[str, Any]:
    raw = state.get("current_draft")
    return dict(raw) if isinstance(raw, dict) else {}


def extract_builder_history(state: dict[str, Any]) -> list[BuilderHistoryEntry]:
    raw = state.get("history")
    if not isinstance(raw, list):
        return []
    entries: list[BuilderHistoryEntry] = []
    for item in raw:
        if isinstance(item, dict):
            entries.append(BuilderHistoryEntry(**item))
    return entries


def extract_applied_action_ids(state: dict[str, Any]) -> list[str]:
    raw = state.get("applied_action_ids")
    if isinstance(raw, list):
        return [str(item) for item in raw if isinstance(item, str)]
    return []


# ---------------------------------------------------------------------------
# Core transaction logic
# ---------------------------------------------------------------------------


class BuilderTransactionService:
    """Encapsulates builder action preview, apply, and history operations.

    Keeps Brain as a recommendation producer; WorkflowCore owns patch
    validation and persistence.
    """

    def generate_preview(self, workspace: TaskWorkspace) -> BuilderPreviewResponse:
        """Generate a builder preview from Brain analysis."""
        generated_at = _utc_now()
        metadata = workspace.metadata or {}
        state = extract_builder_state(metadata)
        current_draft = extract_builder_draft(state)
        failure_policy = current_draft.get("failurePolicy")
        brain_config = current_draft.get("brainConfig")
        preferred_mode = _preferred_brain_mode(workspace.mode)
        if isinstance(brain_config, dict):
            candidate = brain_config.get("preferredMode")
            if candidate in {"plan", "research", "quant", "policy"}:
                preferred_mode = candidate

        constraints = [
            f"task_mode:{workspace.mode}",
            f"task_status:{workspace.status}",
            f"workflow_mode:{_workflow_mode_for_workspace(workspace.mode)}",
        ]
        if isinstance(failure_policy, dict):
            on_final_failure = failure_policy.get("onFinalFailure")
            max_total_steps = failure_policy.get("maxTotalSteps")
            if isinstance(on_final_failure, str) and on_final_failure.strip():
                constraints.append(f"on_final_failure:{on_final_failure}")
            if isinstance(max_total_steps, int):
                constraints.append(f"max_total_steps:{max_total_steps}")

        context = BrainTaskContext(
            thread_id=workspace.task_id,
            user_goal=workspace.goal,
            constraints=constraints,
            evidence=[workspace.summary] if workspace.summary.strip() else [],
            preferred_mode=preferred_mode,
            factor_candidates=[],
            risk_limits=[],
            memory_hints=[],
        )

        if workspace.goal.strip():
            brain_response = BrainCoreService().run(context)
            builder_action_model = brain_response.builder_action_model
            summary = builder_action_model.summary
        else:
            builder_action_model = BrainBuilderActionModel(
                summary="Add a task goal to generate Brain builder actions.",
                auto_actions=[],
                manual_actions=[],
                apply_all_patch={},
            )
            summary = builder_action_model.summary

        # Detect potential conflicts with stale draft
        conflict_warnings: list[str] = []
        revision = int(state.get("revision") or 0)
        if revision > 0 and current_draft:
            for action in builder_action_model.auto_actions:
                if action.patch:
                    for key in action.patch:
                        if key in current_draft and current_draft[key] != action.patch[key]:
                            conflict_warnings.append(f"Action '{action.id}' modifies '{key}' which already has a draft value")

        return BuilderPreviewResponse(
            task_id=workspace.task_id,
            generated_at=generated_at,
            summary=summary,
            builder_action_model=builder_action_model,
            current_draft=current_draft,
            revision=revision,
            applied_action_ids=extract_applied_action_ids(state),
            history=extract_builder_history(state),
            conflict_warnings=conflict_warnings,
        )

    def apply_action(
        self,
        workspace: TaskWorkspace,
        preview: BuilderPreviewResponse,
        action_id: str,
    ) -> tuple[BuilderApplyResponse, dict[str, Any]]:
        """Apply a single builder action. Returns (response, new_builder_state)."""
        actions = preview.builder_action_model.auto_actions + preview.builder_action_model.manual_actions
        action = next((item for item in actions if item.id == action_id), None)
        if action is None:
            raise ValueError(f"Builder action '{action_id}' not found in preview")
        if not action.patch:
            raise ValueError("Selected builder action does not expose an apply patch")

        next_draft = deep_merge_patch(preview.current_draft, action.patch)
        return self._write_transaction(
            workspace=workspace,
            next_draft=next_draft,
            action_ids=[action.id],
            action_title=action.title,
            patch=action.patch,
        )

    def apply_batch(
        self,
        workspace: TaskWorkspace,
        preview: BuilderPreviewResponse,
        *,
        action_ids: list[str] | None = None,
        use_apply_all_patch: bool = False,
    ) -> tuple[BuilderApplyResponse, dict[str, Any]]:
        """Apply multiple builder actions as a single transaction."""
        auto_actions = [a for a in preview.builder_action_model.auto_actions if a.patch]
        action_index = {a.id: a for a in auto_actions}
        selected_actions = auto_actions if use_apply_all_patch or not action_ids else [action_index[aid] for aid in action_ids if aid in action_index]
        if not selected_actions:
            raise ValueError("No auto-applicable builder actions were selected")

        if use_apply_all_patch:
            patch = preview.builder_action_model.apply_all_patch
            ids = [a.id for a in auto_actions]
            title = "Apply all Brain builder actions"
        else:
            patch: dict[str, Any] = {}
            for action in selected_actions:
                patch = deep_merge_patch(patch, action.patch)
            ids = [a.id for a in selected_actions]
            title = f"Apply {len(selected_actions)} Brain builder actions"

        next_draft = deep_merge_patch(preview.current_draft, patch)
        return self._write_transaction(
            workspace=workspace,
            next_draft=next_draft,
            action_ids=ids,
            action_title=title,
            patch=patch,
        )

    def get_history(self, workspace: TaskWorkspace) -> BuilderHistoryResponse:
        """Return the builder transaction history for a workspace."""
        metadata = workspace.metadata or {}
        state = extract_builder_state(metadata)
        return BuilderHistoryResponse(
            task_id=workspace.task_id,
            revision=int(state.get("revision") or 0),
            current_draft=extract_builder_draft(state),
            applied_action_ids=extract_applied_action_ids(state),
            history=extract_builder_history(state),
        )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _write_transaction(
        self,
        *,
        workspace: TaskWorkspace,
        next_draft: dict[str, Any],
        action_ids: list[str],
        action_title: str,
        patch: dict[str, Any],
    ) -> tuple[BuilderApplyResponse, dict[str, Any]]:
        """Create a transaction entry and return (response, new_builder_state_dict)."""
        metadata = workspace.metadata or {}
        state = extract_builder_state(metadata)
        history = extract_builder_history(state)
        applied_action_ids = extract_applied_action_ids(state)
        revision = int(state.get("revision") or 0) + 1
        applied_at = _utc_now()
        transaction_id = f"builder-txn-{uuid4().hex}"

        history_entry = BuilderHistoryEntry(
            transaction_id=transaction_id,
            revision=revision,
            applied_at=applied_at,
            action_ids=action_ids,
            action_title=action_title,
            patch=patch,
            source="brain",
            applied_by="operator",
        )
        next_action_ids = list(dict.fromkeys([*applied_action_ids, *action_ids]))
        next_history = [history_entry, *history][:20]
        next_state = {
            "revision": revision,
            "current_draft": next_draft,
            "applied_action_ids": next_action_ids,
            "history": [entry.model_dump(mode="json") for entry in next_history],
            "last_applied_at": applied_at,
        }

        affected_keys = list(patch.keys()) if isinstance(patch, dict) else []

        response = BuilderApplyResponse(
            task_id=workspace.task_id,
            transaction_id=transaction_id,
            status="applied",
            revision=revision,
            current_draft=next_draft,
            applied_action_ids=next_action_ids,
            history=next_history,
            affected_keys=affected_keys,
        )
        return response, next_state
