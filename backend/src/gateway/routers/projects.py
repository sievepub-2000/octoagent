"""Long-lived project contexts and defaults."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.runtime.config.app_config import get_app_config
from src.storage.project.service import get_project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _validate_default_model(model_name: str | None) -> None:
    if model_name and get_app_config().get_model_config(model_name) is None:
        raise HTTPException(status_code=400, detail=f"Unknown default model: {model_name}")


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    root_path: str = Field(min_length=1)
    instructions: str = Field(default="", max_length=20_000)
    default_model: str = ""
    permission_mode: Literal["approval", "directory", "system"] = "directory"


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    root_path: str | None = None
    instructions: str | None = Field(default=None, max_length=20_000)
    default_model: str | None = None
    permission_mode: Literal["approval", "directory", "system"] | None = None
    status: Literal["active", "archived"] | None = None
    pinned_files: list[str] | None = None
    memory_summary: str | None = Field(default=None, max_length=20_000)


@router.get("")
async def list_projects(include_archived: bool = Query(default=False)) -> list[dict]:
    return get_project_service().list_projects(include_archived=include_archived)


@router.post("", status_code=201)
async def create_project(body: ProjectCreateRequest) -> dict:
    _validate_default_model(body.default_model)
    try:
        return get_project_service().create_project(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/system/summaries")
async def list_all_project_summaries() -> list[dict]:
    return get_project_service().list_projects(include_archived=True)


@router.get("/{project_id}")
async def get_project(project_id: str) -> dict:
    project = get_project_service().get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}")
async def update_project(project_id: str, body: ProjectUpdateRequest) -> dict:
    _validate_default_model(body.default_model)
    try:
        project = get_project_service().update_project(project_id, **body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/context")
async def get_project_context(project_id: str) -> dict:
    try:
        context = get_project_service().resolve_execution_context(project_id)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if detail.startswith("Project not found") else 409, detail=detail) from exc
    return context.model_dump(mode="json")
