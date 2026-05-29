import asyncio
import logging
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.gateway.path_utils import resolve_thread_virtual_path
from src.runtime.config.extensions_config import ExtensionsConfig, SkillStateConfig, get_extensions_config, reload_extensions_config
from src.storage.skills import Skill, load_skills
from src.storage.skills.agent_templates import (
    AGENCY_AGENTS_DOWNLOAD_URL,
    install_agency_agents_skill_from_archive,
)
from src.storage.skills.loader import get_skills_root_path, invalidate_skills_cache
from src.utils.agent_tool_guide import async_refresh_agent_tool_guide
from src.utils.json_atomic import write_json_atomic

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["skills"])


class SkillResponse(BaseModel):
    """Response model for skill information."""

    name: str = Field(..., description="Name of the skill")
    description: str = Field(..., description="Description of what the skill does")
    license: str | None = Field(None, description="License information")
    category: str = Field(..., description="Category of the skill (public or custom)")
    enabled: bool = Field(default=True, description="Whether this skill is enabled")


class SkillsListResponse(BaseModel):
    """Response model for listing all skills."""

    skills: list[SkillResponse]


class SkillUpdateRequest(BaseModel):
    """Request model for updating a skill."""

    enabled: bool | None = Field(default=None, description="Whether to enable or disable the skill")
    description: str | None = Field(default=None, description="Updated skill description")
    license: str | None = Field(default=None, description="Updated license value (empty string clears it)")
    content: str | None = Field(default=None, description="Updated SKILL.md body content")


class SkillCreateRequest(BaseModel):
    """Request model for creating a custom skill."""

    name: str = Field(..., description="Skill name (hyphen-case, e.g. my-new-skill)")
    description: str = Field(..., description="Description of what the skill does")
    license: str | None = Field(default=None, description="License information")
    content: str | None = Field(default=None, description="Optional additional SKILL.md body content")


class SkillInstallRequest(BaseModel):
    """Request model for installing a skill from a .skill file."""

    thread_id: str = Field(..., description="The thread ID where the .skill file is located")
    path: str = Field(..., description="Virtual path to the .skill file (e.g., mnt/user-data/outputs/my-skill.skill)")


class SkillInstallResponse(BaseModel):
    """Response model for skill installation."""

    success: bool = Field(..., description="Whether the installation was successful")
    skill_name: str = Field(..., description="Name of the installed skill")
    message: str = Field(..., description="Installation result message")


class AgencyAgentsInstallResponse(BaseModel):
    """Response model for installing the upstream Agency Agents bundle."""

    success: bool = Field(..., description="Whether the installation was successful")
    skill_name: str = Field(..., description="Installed aggregate skill name")
    template_count: int = Field(..., description="Number of parsed agent templates")
    message: str = Field(..., description="Installation result message")


# Allowed properties in SKILL.md frontmatter
ALLOWED_FRONTMATTER_PROPERTIES = {"name", "description", "license", "allowed-tools", "metadata"}


def _validate_skill_frontmatter(skill_dir: Path) -> tuple[bool, str, str | None]:
    """Validate a skill directory's SKILL.md frontmatter.

    Args:
        skill_dir: Path to the skill directory containing SKILL.md.

    Returns:
        Tuple of (is_valid, message, skill_name).
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found", None

    content = skill_md.read_text()
    if not content.startswith("---"):
        return False, "No YAML frontmatter found", None

    # Extract frontmatter
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format", None

    frontmatter_text = match.group(1)

    # Parse YAML frontmatter
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter must be a YAML dictionary", None
    except yaml.YAMLError as e:
        return False, f"Invalid YAML in frontmatter: {e}", None

    # Check for unexpected properties
    unexpected_keys = set(frontmatter.keys()) - ALLOWED_FRONTMATTER_PROPERTIES
    if unexpected_keys:
        return False, f"Unexpected key(s) in SKILL.md frontmatter: {', '.join(sorted(unexpected_keys))}", None

    # Check required fields
    if "name" not in frontmatter:
        return False, "Missing 'name' in frontmatter", None
    if "description" not in frontmatter:
        return False, "Missing 'description' in frontmatter", None

    # Validate name
    name = frontmatter.get("name", "")
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}", None
    name = name.strip()
    if not name:
        return False, "Name cannot be empty", None

    # Check naming convention (hyphen-case: lowercase with hyphens)
    if not re.match(r"^[a-z0-9-]+$", name):
        return False, f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)", None
    if name.startswith("-") or name.endswith("-") or "--" in name:
        return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens", None
    if len(name) > 64:
        return False, f"Name is too long ({len(name)} characters). Maximum is 64 characters.", None

    # Validate description
    description = frontmatter.get("description", "")
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}", None
    description = description.strip()
    if description:
        if "<" in description or ">" in description:
            return False, "Description cannot contain angle brackets (< or >)", None
        if len(description) > 1024:
            return False, f"Description is too long ({len(description)} characters). Maximum is 1024 characters.", None

    return True, "Skill is valid!", name


def _skill_to_response(skill: Skill) -> SkillResponse:
    """Convert a Skill object to a SkillResponse."""
    return SkillResponse(
        name=skill.name,
        description=skill.description,
        license=skill.license,
        category=skill.category,
        enabled=skill.enabled,
    )


@router.get(
    "/skills",
    response_model=SkillsListResponse,
    summary="List All Skills",
    description="Retrieve a list of all available skills from both public and custom directories.",
)
async def list_skills() -> SkillsListResponse:
    """List all available skills.

    Returns all skills regardless of their enabled status.

    Returns:
        A list of all skills with their metadata.

    Example Response:
        ```json
        {
            "skills": [
                {
                    "name": "PDF Processing",
                    "description": "Extract and analyze PDF content",
                    "license": "MIT",
                    "category": "public",
                    "enabled": true
                },
                {
                    "name": "Frontend Design",
                    "description": "Generate frontend designs and components",
                    "license": null,
                    "category": "custom",
                    "enabled": false
                }
            ]
        }
        ```
    """
    try:
        # Load all skills (including disabled ones)
        skills = await asyncio.to_thread(load_skills, None, True, False)
        return SkillsListResponse(skills=[_skill_to_response(skill) for skill in skills])
    except Exception as e:
        logger.error(f"Failed to load skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load skills. Check server logs for details.")


@router.get(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Get Skill Details",
    description="Retrieve detailed information about a specific skill by its name.",
)
async def get_skill(skill_name: str) -> SkillResponse:
    """Get a specific skill by name.

    Args:
        skill_name: The name of the skill to retrieve.

    Returns:
        Skill information if found.

    Raises:
        HTTPException: 404 if skill not found.

    Example Response:
        ```json
        {
            "name": "PDF Processing",
            "description": "Extract and analyze PDF content",
            "license": "MIT",
            "category": "public",
            "enabled": true
        }
        ```
    """
    try:
        skills = await asyncio.to_thread(load_skills, None, True, False)
        skill = next((s for s in skills if s.name == skill_name), None)

        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        return _skill_to_response(skill)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill: {str(e)}")


@router.put(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Update Skill",
    description="Update a skill's enabled status by modifying the extensions_config.json file.",
)
async def update_skill(skill_name: str, request: SkillUpdateRequest) -> SkillResponse:
    """Update a skill's enabled status.

    This will modify the extensions_config.json file to update the enabled state.
    The SKILL.md file itself is not modified.

    Args:
        skill_name: The name of the skill to update.
        request: The update request containing the new enabled status.

    Returns:
        The updated skill information.

    Raises:
        HTTPException: 404 if skill not found, 500 if update fails.

    Example Request:
        ```json
        {
            "enabled": false
        }
        ```

    Example Response:
        ```json
        {
            "name": "PDF Processing",
            "description": "Extract and analyze PDF content",
            "license": "MIT",
            "category": "public",
            "enabled": false
        }
        ```
    """
    try:
        if request.enabled is None and request.description is None and request.license is None and request.content is None:
            raise HTTPException(status_code=400, detail="No update fields provided")

        # Find the skill to verify it exists
        skills = load_skills(enabled_only=False)
        skill = next((s for s in skills if s.name == skill_name), None)

        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        update_metadata = request.description is not None or request.license is not None or request.content is not None
        if update_metadata and skill.category != "custom":
            raise HTTPException(
                status_code=403,
                detail=f"Cannot edit built-in skill '{skill_name}'. Only custom skills can be edited.",
            )

        # Get or create config path
        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            # Create new config file in parent directory (project root)
            config_path = Path.cwd().parent / "extensions_config.json"
            logger.info(f"No existing extensions config found. Creating new config at: {config_path}")

        # Load current configuration
        extensions_config = get_extensions_config()

        if request.enabled is not None:
            extensions_config.skills[skill_name] = SkillStateConfig(enabled=request.enabled)

            config_data = extensions_config.to_serializable_dict()

            # Write the configuration to file atomically
            write_json_atomic(config_path, config_data)
            logger.info(f"Skills configuration updated and saved to: {config_path}")

        if update_metadata:
            skills_root = get_skills_root_path()
            skill_md = skills_root / "custom" / skill_name / "SKILL.md"
            if not skill_md.exists():
                raise HTTPException(status_code=404, detail=f"Skill directory for '{skill_name}' not found")

            markdown = skill_md.read_text(encoding="utf-8")
            frontmatter_match = re.match(r"^---\n(.*?)\n---\n?(.*)$", markdown, re.DOTALL)
            if frontmatter_match:
                frontmatter = yaml.safe_load(frontmatter_match.group(1)) or {}
                body = frontmatter_match.group(2)
            else:
                frontmatter = {}
                body = markdown

            if not isinstance(frontmatter, dict):
                frontmatter = {}

            frontmatter["name"] = skill_name
            if request.description is not None:
                frontmatter["description"] = request.description.strip()
            else:
                frontmatter.setdefault("description", skill.description)

            if request.license is not None:
                next_license = request.license.strip()
                if next_license:
                    frontmatter["license"] = next_license
                elif "license" in frontmatter:
                    del frontmatter["license"]

            if request.content is not None:
                body = request.content.strip()

            serialized_frontmatter = yaml.safe_dump(
                frontmatter,
                sort_keys=False,
                allow_unicode=True,
            ).strip()
            next_markdown = f"---\n{serialized_frontmatter}\n---\n"
            if body.strip():
                next_markdown += f"\n{body.strip()}\n"

            skill_md.write_text(next_markdown, encoding="utf-8")
            logger.info("Skill '%s' metadata updated", skill_name)

        # Reload the extensions config to update the global cache
        reload_extensions_config()
        invalidate_skills_cache()

        # Reload the skills to get the updated status (for API response)
        skills = await asyncio.to_thread(load_skills, None, True, False)
        updated_skill = next((s for s in skills if s.name == skill_name), None)

        if updated_skill is None:
            raise HTTPException(status_code=500, detail=f"Failed to reload skill '{skill_name}' after update")

        await async_refresh_agent_tool_guide()
        logger.info("Skill '%s' updated", skill_name)
        return _skill_to_response(updated_skill)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update skill: {str(e)}")


@router.post(
    "/skills",
    response_model=SkillResponse,
    summary="Create a custom skill",
    description="Create a new custom skill with name and description.",
)
async def create_skill(request: SkillCreateRequest) -> SkillResponse:
    """Create a custom skill by generating a SKILL.md in the custom skills directory."""
    import re as _re

    name = request.name.strip()
    if not _re.match(r"^[a-z][a-z0-9-]*$", name):
        raise HTTPException(status_code=422, detail="Skill name must be hyphen-case (e.g. my-skill)")

    skills_root = get_skills_root_path()
    custom_skills_dir = skills_root / "custom"
    custom_skills_dir.mkdir(parents=True, exist_ok=True)

    target_dir = custom_skills_dir / name
    if target_dir.exists():
        raise HTTPException(status_code=409, detail=f"Skill '{name}' already exists")

    target_dir.mkdir(parents=True, exist_ok=True)

    # Build SKILL.md
    frontmatter = {"name": name, "description": request.description.strip()}
    if request.license:
        frontmatter["license"] = request.license.strip()

    md_lines = ["---"]
    for k, v in frontmatter.items():
        md_lines.append(f"{k}: {v}")
    md_lines.append("---")
    md_lines.append("")
    if request.content:
        md_lines.append(request.content.strip())
        md_lines.append("")

    (target_dir / "SKILL.md").write_text("\n".join(md_lines))

    # Reload and return
    invalidate_skills_cache()
    skills = await asyncio.to_thread(load_skills)
    skill = next((s for s in skills if s.name == name), None)
    if not skill:
        raise HTTPException(status_code=500, detail=f"Failed to load newly created skill '{name}'")

    await async_refresh_agent_tool_guide()
    logger.info(f"Skill '{name}' created successfully")
    return _skill_to_response(skill)


@router.post(
    "/skills/install",
    response_model=SkillInstallResponse,
    summary="Install Skill",
    description="Install a skill from a .skill file (ZIP archive) located in the thread's user-data directory.",
)
async def install_skill(request: SkillInstallRequest) -> SkillInstallResponse:
    """Install a skill from a .skill file.

    The .skill file is a ZIP archive containing a skill directory with SKILL.md
    and optional resources (scripts, references, assets).

    Args:
        request: The install request containing thread_id and virtual path to .skill file.

    Returns:
        Installation result with skill name and status message.

    Raises:
        HTTPException:
            - 400 if path is invalid or file is not a valid .skill file
            - 403 if access denied (path traversal detected)
            - 404 if file not found
            - 409 if skill already exists
            - 500 if installation fails

    Example Request:
        ```json
        {
            "thread_id": "abc123-def456",
            "path": "/mnt/user-data/outputs/my-skill.skill"
        }
        ```

    Example Response:
        ```json
        {
            "success": true,
            "skill_name": "my-skill",
            "message": "Skill 'my-skill' installed successfully"
        }
        ```
    """
    try:
        # Resolve the virtual path to actual file path
        skill_file_path = resolve_thread_virtual_path(request.thread_id, request.path)

        # Check if file exists
        if not skill_file_path.exists():
            raise HTTPException(status_code=404, detail=f"Skill file not found: {request.path}")

        # Check if it's a file
        if not skill_file_path.is_file():
            raise HTTPException(status_code=400, detail=f"Path is not a file: {request.path}")

        # Check file extension
        if not skill_file_path.suffix == ".skill":
            raise HTTPException(status_code=400, detail="File must have .skill extension")

        # Verify it's a valid ZIP file
        if not zipfile.is_zipfile(skill_file_path):
            raise HTTPException(status_code=400, detail="File is not a valid ZIP archive")

        # Get the custom skills directory
        skills_root = get_skills_root_path()
        custom_skills_dir = skills_root / "custom"

        # Create custom directory if it doesn't exist
        custom_skills_dir.mkdir(parents=True, exist_ok=True)

        # Extract to a temporary directory first for validation
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Extract the .skill file with zip-slip protection
            with zipfile.ZipFile(skill_file_path, "r") as zip_ref:
                # Validate all member paths before extraction
                for member in zip_ref.namelist():
                    member_path = Path(member)
                    # Reject paths with .. components or absolute paths
                    if ".." in member_path.parts or member_path.is_absolute():
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unsafe path in archive: {member}",
                        )
                    # Verify resolved path stays within temp_path
                    resolved = (temp_path / member).resolve()
                    if not str(resolved).startswith(str(temp_path.resolve())):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Path traversal detected in archive: {member}",
                        )
                # Check total uncompressed size (50 MB limit)
                total_size = sum(info.file_size for info in zip_ref.infolist())
                if total_size > 50 * 1024 * 1024:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Archive too large: {total_size // (1024 * 1024)} MB exceeds 50 MB limit",
                    )
                zip_ref.extractall(temp_path)

            # Find the skill directory (should be the only top-level directory)
            extracted_items = list(temp_path.iterdir())
            if len(extracted_items) == 0:
                raise HTTPException(status_code=400, detail="Skill archive is empty")

            # Handle both cases: single directory or files directly in root
            if len(extracted_items) == 1 and extracted_items[0].is_dir():
                skill_dir = extracted_items[0]
            else:
                # Files are directly in the archive root
                skill_dir = temp_path

            # Validate the skill
            is_valid, message, skill_name = _validate_skill_frontmatter(skill_dir)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"Invalid skill: {message}")

            if not skill_name:
                raise HTTPException(status_code=400, detail="Could not determine skill name")

            # Check if skill already exists
            target_dir = custom_skills_dir / skill_name
            if target_dir.exists():
                raise HTTPException(status_code=409, detail=f"Skill '{skill_name}' already exists. Please remove it first or use a different name.")

            # Move the skill directory to the custom skills directory
            shutil.copytree(skill_dir, target_dir)

        logger.info(f"Skill '{skill_name}' installed successfully to {target_dir}")
        invalidate_skills_cache()
        await asyncio.to_thread(load_skills)
        await async_refresh_agent_tool_guide()
        return SkillInstallResponse(success=True, skill_name=skill_name, message=f"Skill '{skill_name}' installed successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to install skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to install skill: {str(e)}")


@router.post(
    "/skills/install/agency-agents",
    response_model=AgencyAgentsInstallResponse,
    summary="Install Agency Agents",
    description="Download the upstream Agency Agents bundle, convert it into an OctoAgent skill, and expose all agents as reusable templates.",
)
async def install_agency_agents() -> AgencyAgentsInstallResponse:
    try:
        skills_root = get_skills_root_path()
        custom_skills_dir = skills_root / "custom"
        custom_skills_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            response = await client.get(AGENCY_AGENTS_DOWNLOAD_URL)
            response.raise_for_status()
            archive_bytes = response.content

        skill_name, template_count = await asyncio.to_thread(
            install_agency_agents_skill_from_archive,
            archive_bytes,
            custom_skills_dir,
            overwrite=True,
        )

        invalidate_skills_cache()
        await asyncio.to_thread(load_skills)
        await async_refresh_agent_tool_guide()
        message = f"Installed '{skill_name}' with {template_count} agent templates from upstream Agency Agents"
        logger.info(message)
        return AgencyAgentsInstallResponse(
            success=True,
            skill_name=skill_name,
            template_count=template_count,
            message=message,
        )
    except httpx.HTTPError as exc:
        logger.error("Failed to download Agency Agents bundle: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to download Agency Agents bundle: {exc}",
        )
    except Exception as exc:
        logger.error("Failed to install Agency Agents bundle: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to install Agency Agents bundle: {exc}")


class SkillDeleteResponse(BaseModel):
    """Response model for skill deletion."""

    success: bool = Field(..., description="Whether the deletion was successful")
    skill_name: str = Field(..., description="Name of the deleted skill")
    message: str = Field(..., description="Deletion result message")


@router.delete(
    "/skills/{skill_name}",
    response_model=SkillDeleteResponse,
    summary="Delete a custom skill",
    description="Remove a custom skill from the system. Only custom skills can be deleted.",
)
async def delete_skill(skill_name: str) -> SkillDeleteResponse:
    """Delete a custom skill by name."""
    invalidate_skills_cache()
    skills = await asyncio.to_thread(load_skills)
    skill = next((s for s in skills if s.name == skill_name), None)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    if skill.category != "custom":
        raise HTTPException(status_code=403, detail=f"Cannot delete built-in skill '{skill_name}'. Only custom skills can be deleted.")

    skills_root = get_skills_root_path()
    custom_skills_dir = skills_root / "custom"
    target_dir = custom_skills_dir / skill_name

    if not target_dir.exists():
        raise HTTPException(status_code=404, detail=f"Skill directory for '{skill_name}' not found")

    try:
        shutil.rmtree(target_dir)
        invalidate_skills_cache()
        await asyncio.to_thread(load_skills)
        await async_refresh_agent_tool_guide()
        logger.info(f"Skill '{skill_name}' deleted successfully")
        return SkillDeleteResponse(success=True, skill_name=skill_name, message=f"Skill '{skill_name}' deleted successfully")
    except Exception as e:
        logger.error(f"Failed to delete skill '{skill_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete skill: {str(e)}")
