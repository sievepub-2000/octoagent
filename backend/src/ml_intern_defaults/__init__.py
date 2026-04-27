"""ML-Intern default profile integration for OctoAgent agents.

The defaults mirror Hugging Face ml-intern configuration semantics without
vendoring the upstream runtime. Source inspected at:
https://github.com/huggingface/ml-intern @ ff8c636fbb905c4e9a4ba230ed599ab130707c61.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

ML_INTERN_SOURCE_REPO = "https://github.com/huggingface/ml-intern"
ML_INTERN_SOURCE_COMMIT = "ff8c636fbb905c4e9a4ba230ed599ab130707c61"
ML_INTERN_SESSION_DATASET_REPO = "smolagents/ml-intern-sessions"
ML_INTERN_HF_MCP_SERVER = {
    "transport": "http",
    "url": "https://huggingface.co/mcp?login",
}

MLInternProfileName = Literal["interactive", "headless"]


@dataclass(frozen=True, slots=True)
class MLInternProfile:
    name: MLInternProfileName
    workflow_modes: tuple[str, ...]
    preferred_model_name: str
    save_sessions: bool
    session_dataset_repo: str
    yolo_mode: bool
    confirm_cpu_jobs: bool
    auto_file_upload: bool
    max_iterations: int
    reasoning_effort: str
    permission_mode: str
    mcp_servers: dict[str, dict[str, str]]


INTERACTIVE_PROFILE = MLInternProfile(
    name="interactive",
    workflow_modes=("dialogue", "chat", "conversation"),
    preferred_model_name="anthropic/claude-opus-4-6",
    save_sessions=True,
    session_dataset_repo=ML_INTERN_SESSION_DATASET_REPO,
    yolo_mode=False,
    confirm_cpu_jobs=True,
    auto_file_upload=True,
    max_iterations=300,
    reasoning_effort="max",
    permission_mode="workspace",
    mcp_servers={"hf-mcp-server": ML_INTERN_HF_MCP_SERVER},
)

HEADLESS_PROFILE = MLInternProfile(
    name="headless",
    workflow_modes=("scheduled", "timed", "yolo", "auto"),
    preferred_model_name="anthropic/claude-opus-4-6",
    save_sessions=True,
    session_dataset_repo=ML_INTERN_SESSION_DATASET_REPO,
    yolo_mode=True,
    confirm_cpu_jobs=False,
    auto_file_upload=True,
    max_iterations=300,
    reasoning_effort="max",
    permission_mode="yolo",
    mcp_servers={"hf-mcp-server": ML_INTERN_HF_MCP_SERVER},
)

_PROFILES: dict[str, MLInternProfile] = {
    INTERACTIVE_PROFILE.name: INTERACTIVE_PROFILE,
    HEADLESS_PROFILE.name: HEADLESS_PROFILE,
}
_HEADLESS_MODE_VALUES = {"headless", "scheduled", "schedule", "timed", "timer", "yolo", "auto"}


def normalize_profile_name(value: Any) -> MLInternProfileName | None:
    candidate = str(value or "").strip().lower().replace("_", "-")
    if candidate in {"interactive", "interractive", "dialogue", "conversation", "chat"}:
        return "interactive"
    if candidate in _HEADLESS_MODE_VALUES:
        return "headless"
    return None


def resolve_ml_intern_profile_name(
    value: Any = None,
    *,
    permission_mode: Any = None,
    workflow_run_mode: Any = None,
    workflow_mode: Any = None,
    yolo_mode: Any = None,
    context: dict[str, Any] | None = None,
) -> MLInternProfileName:
    context = dict(context or {})
    explicit = normalize_profile_name(
        value
        or context.get("ml_intern_profile")
        or context.get("mlInternProfile")
        or context.get("ml_intern_mode")
        or context.get("mlInternMode")
    )
    if explicit:
        return explicit

    permission = str(permission_mode or context.get("permission_mode") or "").strip().lower()
    if permission == "yolo":
        return "headless"

    run_mode = normalize_profile_name(
        workflow_run_mode
        or workflow_mode
        or context.get("workflow_run_mode")
        or context.get("workflowRunMode")
        or context.get("mode")
    )
    if run_mode == "headless":
        return "headless"

    if bool(yolo_mode) or bool(context.get("yolo_mode")) or bool(context.get("yoloMode")):
        return "headless"
    return "interactive"


def get_ml_intern_profile(name: Any = None, **kwargs: Any) -> MLInternProfile:
    return _PROFILES[resolve_ml_intern_profile_name(name, **kwargs)]


def build_ml_intern_runtime_context(name: Any = None, **kwargs: Any) -> dict[str, Any]:
    profile = get_ml_intern_profile(name, **kwargs)
    payload = asdict(profile)
    payload["source_repo"] = ML_INTERN_SOURCE_REPO
    payload["source_commit"] = ML_INTERN_SOURCE_COMMIT
    return {
        "ml_intern_profile": profile.name,
        "ml_intern_defaults": payload,
    }


def build_ml_intern_prompt_section(name: Any = None, **kwargs: Any) -> str:
    profile = get_ml_intern_profile(name, **kwargs)
    mode_line = (
        "Dialogue/chat workflow: use the interactive profile. Ask before expensive training, CPU jobs, dataset writes, or publishing."
        if profile.name == "interactive"
        else "Scheduled/timed/YOLO workflow: use the headless profile. Execute approved work directly, keep a concrete audit trail, and avoid clarification loops unless blocked."
    )
    return f"""<ml_intern_defaults source=\"{ML_INTERN_SOURCE_REPO}\" commit=\"{ML_INTERN_SOURCE_COMMIT}\" active_profile=\"{profile.name}\">
OctoAgent uses Hugging Face ml-intern defaults as the baseline for every agent.
- Profile mapping: interactive/interractive/dialogue/chat -> interactive; headless/scheduled/timed/yolo/auto -> headless.
- Active behavior: {mode_line}
- Hugging Face work should research official docs and current model/dataset cards before implementation.
- Verify dataset IDs, model IDs, licenses, private repo access, hardware assumptions, and HF_TOKEN requirements before side effects.
- Prefer the configured Hugging Face MCP server when available: hf-mcp-server at https://huggingface.co/mcp?login.
- Session saving target follows ml-intern semantics: {ML_INTERN_SESSION_DATASET_REPO}.
- Iteration cap: {profile.max_iterations}; reasoning effort hint: {profile.reasoning_effort}; auto file upload: {str(profile.auto_file_upload).lower()}.
- Never expose tokens or secrets. Summarize uploaded files, job IDs, repo IDs, and URLs precisely.
</ml_intern_defaults>"""

