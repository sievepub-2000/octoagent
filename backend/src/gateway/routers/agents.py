"""CRUD API for custom agents."""

import asyncio
import logging
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.runtime.config.agents_config import AgentConfig, list_custom_agents, load_agent_config, load_agent_soul, load_system_agent
from src.runtime.config.paths import get_paths
from src.storage.skills import load_skills
from src.storage.skills.agent_templates import list_agent_template_summaries, load_agent_template_detail

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["agents"])

AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")
THREAD_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class AgentResponse(BaseModel):
    """Response model for a custom agent."""

    id: str | None = Field(default=None, description="Stable UI identifier for this agent entry")
    name: str = Field(..., description="Agent name (hyphen-case)")
    display_name: str | None = Field(default=None, description="Human readable display name")
    description: str = Field(default="", description="Agent description")
    model: str | None = Field(default=None, description="Optional model override")
    tool_groups: list[str] | None = Field(default=None, description="Optional tool group whitelist")
    soul: str | None = Field(default=None, description="SOUL.md content (included on GET /{name})")
    avatar: str | None = Field(default=None, description="Avatar filename if custom avatar exists")
    source: Literal["custom", "template", "system"] = Field(default="custom", description="Where this agent entry comes from")
    editable: bool = Field(default=True, description="Whether this entry can be edited through /api/agents/{name}")
    deletable: bool = Field(default=True, description="Whether this entry can be deleted through /api/agents/{name}")
    chat_enabled: bool = Field(default=True, description="Whether this entry can start a direct chat")
    template_skill_name: str | None = Field(default=None, description="Source skill for template-backed entries")
    template_id: str | None = Field(default=None, description="Template identifier for template-backed entries")
    source_category: str | None = Field(default=None, description="Template source category")
    source_path: str | None = Field(default=None, description="Template source path")


class AgentsListResponse(BaseModel):
    """Response model for listing all custom agents."""

    agents: list[AgentResponse]


class AgentTemplateSummaryResponse(BaseModel):
    """Summary of an agent template exported by an installed skill."""

    skill_name: str = Field(..., description="The skill providing the template")
    skill_enabled: bool = Field(default=True, description="Whether the source skill is enabled")
    template_id: str = Field(..., description="Stable template identifier within the skill")
    name: str = Field(..., description="Human readable template name")
    description: str = Field(default="", description="Short template description")
    source_category: str | None = Field(default=None, description="Original upstream category or division")
    source_path: str | None = Field(default=None, description="Original upstream source file path")
    color: str | None = Field(default=None, description="Optional upstream display color")


class AgentTemplateListResponse(BaseModel):
    """Response model for listing exported agent templates."""

    templates: list[AgentTemplateSummaryResponse]


class AgentTemplateDetailResponse(AgentTemplateSummaryResponse):
    """Detailed agent template payload used to prefill custom agent creation."""

    model: str | None = Field(default=None, description="Optional model override for the template")
    tool_groups: list[str] | None = Field(default=None, description="Optional tool group whitelist")
    soul: str = Field(default="", description="SOUL-compatible markdown body")


class AgentCreateRequest(BaseModel):
    """Request body for creating a custom agent."""

    name: str = Field(..., description="Agent name (must match ^[A-Za-z0-9-]+$, stored as lowercase)")
    description: str = Field(default="", description="Agent description")
    model: str | None = Field(default=None, description="Optional model override")
    tool_groups: list[str] | None = Field(default=None, description="Optional tool group whitelist")
    soul: str = Field(default="", description="SOUL.md content — agent personality and behavioral guardrails")


class AgentUpdateRequest(BaseModel):
    """Request body for updating a custom agent."""

    name: str | None = Field(default=None, description="New agent name (triggers rename)")
    description: str | None = Field(default=None, description="Updated description")
    model: str | None = Field(default=None, description="Updated model override")
    tool_groups: list[str] | None = Field(default=None, description="Updated tool group whitelist")
    soul: str | None = Field(default=None, description="Updated SOUL.md content")


class AgentConversationArchiveMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    created_at: str | None = None


class AgentConversationArchiveRequest(BaseModel):
    title: str | None = Field(default=None, description="Thread title")
    updated_at: str | None = Field(default=None, description="Last update timestamp")
    continuation: dict[str, Any] | None = Field(default=None, description="Optional continuation metadata")
    messages: list[AgentConversationArchiveMessage] = Field(default_factory=list)


def _validate_agent_name(name: str) -> None:
    """Validate agent name against allowed pattern.

    Args:
        name: The agent name to validate.

    Raises:
        HTTPException: 422 if the name is invalid.
    """
    if not AGENT_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid agent name '{name}'. Must match ^[A-Za-z0-9-]+$ (letters, digits, and hyphens only).",
        )


def _normalize_agent_name(name: str) -> str:
    """Normalize agent name to lowercase for filesystem storage."""
    return name.lower()


def _validate_thread_id(thread_id: str) -> None:
    if not THREAD_ID_PATTERN.match(thread_id):
        raise HTTPException(
            status_code=422,
            detail=(f"Invalid thread id '{thread_id}'. Only letters, digits, underscores, and hyphens are allowed."),
        )


def _conversation_archive_paths(agent_name: str, thread_id: str) -> tuple[Path, Path]:
    conversations_dir = get_paths().agent_dir(agent_name) / "conversations"
    conversations_dir.mkdir(parents=True, exist_ok=True)
    return conversations_dir / f"{thread_id}.json", conversations_dir / f"{thread_id}.md"


def _conversation_archive_markdown(
    agent_name: str,
    thread_id: str,
    request: AgentConversationArchiveRequest,
) -> str:
    lines = [
        f"# {request.title or thread_id}",
        "",
        f"- Agent: `{agent_name}`",
        f"- Thread ID: `{thread_id}`",
        f"- Updated At: `{request.updated_at or datetime.now(UTC).isoformat()}`",
        f"- Message Count: `{len(request.messages)}`",
        "",
    ]
    if request.continuation:
        lines.extend(
            [
                "## Continuation",
                "",
                "```json",
                yaml.safe_dump(request.continuation, allow_unicode=True, sort_keys=True).strip(),
                "```",
                "",
            ]
        )
    lines.extend(["## Messages", ""])
    if not request.messages:
        lines.append("_No messages archived yet._")
        return "\n".join(lines) + "\n"
    for message in request.messages:
        lines.extend(
            [
                f"### {message.role.upper()}" + (f" · {message.created_at}" if message.created_at else ""),
                "",
                message.content.strip() or "_No content._",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


ALLOWED_AVATAR_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2 MB


def _find_agent_avatar(agent_name: str) -> str | None:
    """Find avatar file in agent directory, return filename or None."""
    agent_dir = get_paths().agent_dir(agent_name)
    for ext in ALLOWED_AVATAR_EXTENSIONS:
        candidate = agent_dir / f"avatar{ext}"
        if candidate.exists():
            return candidate.name
    return None


def _agent_config_to_response(
    agent_cfg: AgentConfig,
    include_soul: bool = False,
    *,
    source: str = "custom",
    editable: bool = True,
    deletable: bool = True,
    chat_enabled: bool = True,
    soul_override: str | None = None,
) -> AgentResponse:
    """Convert AgentConfig to AgentResponse."""
    soul: str | None = None
    if soul_override is not None:
        soul = soul_override
    elif include_soul:
        soul = load_agent_soul(agent_cfg.name) or ""

    avatar = _find_agent_avatar(agent_cfg.name) if source == "custom" else None

    return AgentResponse(
        id=f"{source}:{agent_cfg.name}",
        name=agent_cfg.name,
        display_name=agent_cfg.name,
        description=agent_cfg.description,
        model=agent_cfg.model,
        tool_groups=agent_cfg.tool_groups,
        soul=soul,
        avatar=avatar,
        source=source,  # type: ignore[arg-type]
        editable=editable,
        deletable=deletable,
        chat_enabled=chat_enabled,
    )


def _template_summary_to_agent_response(template: Any) -> AgentResponse:
    if hasattr(template, "model_dump"):
        template = template.model_dump()
    elif not isinstance(template, dict):
        template = dict(template)
    skill_name = str(template.get("skill_name") or "").strip()
    template_id = str(template.get("template_id") or "").strip()
    display_name = str(template.get("name") or template_id or skill_name).strip()
    return AgentResponse(
        id=f"template:{skill_name}:{template_id}",
        name=display_name,
        display_name=display_name,
        description=str(template.get("description") or ""),
        model=None,
        tool_groups=None,
        soul=None,
        avatar=None,
        source="template",
        editable=False,
        deletable=False,
        chat_enabled=False,
        template_skill_name=skill_name or None,
        template_id=template_id or None,
        source_category=template.get("source_category"),
        source_path=template.get("source_path"),
    )


@router.get(
    "/agents",
    response_model=AgentsListResponse,
    summary="List Custom Agents",
    description="List all custom agents available in the agents directory.",
)
async def list_agents() -> AgentsListResponse:
    """List custom agents and installed agent templates.

    Returns:
        List of custom agents plus template-backed entries from enabled skills.
    """
    try:
        custom_agents = await asyncio.to_thread(list_custom_agents)
        skills = await asyncio.to_thread(load_skills, None, True, False)
        templates = await asyncio.to_thread(list_agent_template_summaries, skills)
        entries = [_agent_config_to_response(agent) for agent in custom_agents]
        entries.extend(_template_summary_to_agent_response(template) for template in templates)
        return AgentsListResponse(agents=entries)
    except Exception as e:
        logger.error(f"Failed to list agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list agents")


@router.get(
    "/agents/check",
    summary="Check Agent Name",
    description="Validate an agent name and check if it is available (case-insensitive).",
)
def check_agent_name(name: str) -> dict:
    """Check whether an agent name is valid and not yet taken.

    Args:
        name: The agent name to check.

    Returns:
        ``{"available": true/false, "name": "<normalized>"}``

    Raises:
        HTTPException: 422 if the name is invalid.
    """
    _validate_agent_name(name)
    normalized = _normalize_agent_name(name)
    available = not get_paths().agent_dir(normalized).exists()
    return {"available": available, "name": normalized}


@router.get(
    "/agent-templates",
    response_model=AgentTemplateListResponse,
    summary="List Agent Templates",
    description="List agent templates exported by installed skills so they can be used when creating a custom agent.",
)
async def list_agent_templates() -> AgentTemplateListResponse:
    try:
        skills = await asyncio.to_thread(load_skills, None, True, False)
        templates = await asyncio.to_thread(list_agent_template_summaries, skills)
        return AgentTemplateListResponse(templates=[AgentTemplateSummaryResponse.model_validate(template) for template in templates])
    except Exception as exc:
        logger.error("Failed to list agent templates: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list agent templates")


@router.get(
    "/agent-templates/{skill_name}/{template_id}",
    response_model=AgentTemplateDetailResponse,
    summary="Get Agent Template",
    description="Load a specific skill-exported agent template for prefilling custom agent creation.",
)
async def get_agent_template(skill_name: str, template_id: str) -> AgentTemplateDetailResponse:
    try:
        skills = await asyncio.to_thread(load_skills, None, True, False)
        template = await asyncio.to_thread(load_agent_template_detail, skills, skill_name, template_id)
        if template is None:
            raise HTTPException(
                status_code=404,
                detail=f"Agent template '{skill_name}/{template_id}' not found",
            )
        return AgentTemplateDetailResponse.model_validate(template)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to load agent template %s/%s: %s", skill_name, template_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load agent template")


@router.get(
    "/agents/{name}",
    response_model=AgentResponse,
    summary="Get Custom Agent",
    description="Retrieve details and SOUL.md content for a specific custom agent.",
)
def get_agent(name: str) -> AgentResponse:
    """Get a specific custom agent by name.

    Args:
        name: The agent name.

    Returns:
        Agent details including SOUL.md content.

    Raises:
        HTTPException: 404 if agent not found.
    """
    _validate_agent_name(name)
    name = _normalize_agent_name(name)

    try:
        agent_cfg = load_agent_config(name)
        return _agent_config_to_response(agent_cfg, include_soul=True)
    except FileNotFoundError:
        system = load_system_agent(name)
        if system is not None:
            sys_cfg, sys_body = system
            return _agent_config_to_response(
                sys_cfg,
                source="system",
                editable=False,
                deletable=False,
                chat_enabled=True,
                soul_override=sys_body.strip() or None,
            )
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    except Exception as e:
        logger.error(f"Failed to get agent '{name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get agent: {str(e)}")


@router.post(
    "/agents",
    response_model=AgentResponse,
    status_code=201,
    summary="Create Custom Agent",
    description="Create a new custom agent with its config and SOUL.md.",
)
def create_agent_endpoint(request: AgentCreateRequest) -> AgentResponse:
    """Create a new custom agent.

    Args:
        request: The agent creation request.

    Returns:
        The created agent details.

    Raises:
        HTTPException: 409 if agent already exists, 422 if name is invalid.
    """
    _validate_agent_name(request.name)
    normalized_name = _normalize_agent_name(request.name)

    agent_dir = get_paths().agent_dir(normalized_name)

    if agent_dir.exists():
        raise HTTPException(status_code=409, detail=f"Agent '{normalized_name}' already exists")

    try:
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Write config.yaml
        config_data: dict = {"name": normalized_name}
        if request.description:
            config_data["description"] = request.description
        if request.model is not None:
            config_data["model"] = request.model
        if request.tool_groups is not None:
            config_data["tool_groups"] = request.tool_groups

        config_file = agent_dir / "config.yaml"

        def _write_agent_files() -> None:
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
            soul_file = agent_dir / "SOUL.md"
            soul_file.write_text(request.soul, encoding="utf-8")

        _write_agent_files()

        logger.info(f"Created agent '{normalized_name}' at {agent_dir}")

        agent_cfg = load_agent_config(normalized_name)
        return _agent_config_to_response(agent_cfg, include_soul=True)

    except HTTPException:
        raise
    except Exception as e:
        # Clean up on failure
        if agent_dir.exists():
            shutil.rmtree(agent_dir)
        logger.error(f"Failed to create agent '{request.name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")


@router.put(
    "/agents/{name}",
    response_model=AgentResponse,
    summary="Update Custom Agent",
    description="Update an existing custom agent's config and/or SOUL.md.",
)
def update_agent(name: str, request: AgentUpdateRequest) -> AgentResponse:
    """Update an existing custom agent.

    Args:
        name: The agent name.
        request: The update request (all fields optional).

    Returns:
        The updated agent details.

    Raises:
        HTTPException: 404 if agent not found.
    """
    _validate_agent_name(name)
    name = _normalize_agent_name(name)

    try:
        agent_cfg = load_agent_config(name)
    except FileNotFoundError:
        if load_system_agent(name) is not None:
            raise HTTPException(status_code=403, detail=f"Agent '{name}' is system-provided and read-only")
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    agent_dir = get_paths().agent_dir(name)

    # ── Handle rename ────────────────────────────────────────────────
    new_name: str | None = None
    if request.name is not None:
        new_name = _normalize_agent_name(request.name)
        _validate_agent_name(new_name)
        if new_name != name:
            new_dir = get_paths().agent_dir(new_name)
            if new_dir.exists():
                raise HTTPException(
                    status_code=409,
                    detail=f"Agent '{new_name}' already exists — cannot rename.",
                )
            agent_dir.rename(new_dir)
            agent_dir = new_dir
            name = new_name
            logger.info(f"Renamed agent to '{name}'")

    try:
        # Update config if any config fields changed
        config_changed = any(v is not None for v in [request.description, request.model, request.tool_groups, new_name])

        if config_changed:
            updated: dict = {
                "name": name,
                "description": request.description if request.description is not None else agent_cfg.description,
            }
            new_model = request.model if request.model is not None else agent_cfg.model
            if new_model is not None:
                updated["model"] = new_model

            new_tool_groups = request.tool_groups if request.tool_groups is not None else agent_cfg.tool_groups
            if new_tool_groups is not None:
                updated["tool_groups"] = new_tool_groups

            config_file = agent_dir / "config.yaml"

            def _write_config() -> None:
                with open(config_file, "w", encoding="utf-8") as f:
                    yaml.dump(updated, f, default_flow_style=False, allow_unicode=True)

            _write_config()

        # Update SOUL.md if provided
        if request.soul is not None:
            soul_path = agent_dir / "SOUL.md"
            soul_path.write_text(request.soul, encoding="utf-8")

        logger.info(f"Updated agent '{name}'")

        refreshed_cfg = load_agent_config(name)
        return _agent_config_to_response(refreshed_cfg, include_soul=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent '{name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update agent: {str(e)}")


class UserProfileResponse(BaseModel):
    """Response model for the global user profile (USER.md)."""

    content: str | None = Field(default=None, description="USER.md content, or null if not yet created")


class UserProfileUpdateRequest(BaseModel):
    """Request body for setting the global user profile."""

    content: str = Field(default="", description="USER.md content — describes the user's background and preferences")


@router.put(
    "/agents/{name}/conversations/{thread_id}",
    summary="Archive Agent Conversation",
    description="Persist a rendered agent conversation snapshot under default/agents/<agent>/conversations/.",
)
async def archive_agent_conversation(
    name: str,
    thread_id: str,
    request: AgentConversationArchiveRequest,
) -> dict[str, Any]:
    _validate_agent_name(name)
    _validate_thread_id(thread_id)
    name = _normalize_agent_name(name)

    agent_dir = get_paths().agent_dir(name)
    if not agent_dir.exists():
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    json_path, markdown_path = _conversation_archive_paths(name, thread_id)
    payload = {
        "agent_name": name,
        "thread_id": thread_id,
        "title": request.title,
        "updated_at": request.updated_at or datetime.now(UTC).isoformat(),
        "continuation": request.continuation,
        "messages": [message.model_dump(mode="json") for message in request.messages],
    }

    def _write_archive() -> None:
        json_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        markdown_path.write_text(
            _conversation_archive_markdown(name, thread_id, request),
            encoding="utf-8",
        )

    await asyncio.to_thread(_write_archive)
    return {
        "thread_id": thread_id,
        "message_count": len(request.messages),
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


@router.delete(
    "/agents/{name}",
    status_code=204,
    summary="Delete Custom Agent",
    description="Delete a custom agent and all its files (config, SOUL.md, memory).",
)
def delete_agent(name: str) -> None:
    """Delete a custom agent.

    Args:
        name: The agent name.

    Raises:
        HTTPException: 404 if agent not found.
    """
    _validate_agent_name(name)
    name = _normalize_agent_name(name)

    agent_dir = get_paths().agent_dir(name)

    if not agent_dir.exists():
        if load_system_agent(name) is not None:
            raise HTTPException(status_code=403, detail=f"Agent '{name}' is system-provided and read-only")
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    try:
        shutil.rmtree(agent_dir)
        logger.info(f"Deleted agent '{name}' from {agent_dir}")
    except Exception as e:
        logger.error(f"Failed to delete agent '{name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete agent: {str(e)}")


# ─── Avatar endpoints ───


@router.post(
    "/agents/{name}/avatar",
    summary="Upload Agent Avatar",
    description="Upload a custom avatar image for an agent. Max 2 MB. Accepts png, jpg, jpeg, gif, webp, svg.",
)
async def upload_agent_avatar(name: str, file: UploadFile) -> dict:
    """Upload or replace the avatar for a custom agent."""
    _validate_agent_name(name)
    name = _normalize_agent_name(name)

    agent_dir = get_paths().agent_dir(name)
    if not agent_dir.exists():
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    import os

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_AVATAR_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_AVATAR_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size is {MAX_AVATAR_SIZE // 1024 // 1024} MB.")

    # Remove any existing avatar files
    for old_ext in ALLOWED_AVATAR_EXTENSIONS:
        old_file = agent_dir / f"avatar{old_ext}"
        if old_file.exists():
            old_file.unlink()

    avatar_path = agent_dir / f"avatar{ext}"

    def _write_avatar() -> None:
        avatar_path.write_bytes(content)

    await asyncio.to_thread(_write_avatar)
    logger.info(f"Uploaded avatar for agent '{name}': {avatar_path.name}")

    return {"avatar": avatar_path.name, "size": len(content)}


@router.get(
    "/agents/{name}/avatar",
    summary="Get Agent Avatar",
    description="Retrieve the avatar image file for an agent.",
)
async def get_agent_avatar(name: str) -> FileResponse:
    """Serve the agent's avatar image file."""
    _validate_agent_name(name)
    name = _normalize_agent_name(name)

    agent_dir = get_paths().agent_dir(name)
    if not agent_dir.exists():
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    avatar_filename = _find_agent_avatar(name)
    if not avatar_filename:
        raise HTTPException(status_code=404, detail="No avatar found for this agent")

    avatar_path = agent_dir / avatar_filename
    return FileResponse(str(avatar_path))
