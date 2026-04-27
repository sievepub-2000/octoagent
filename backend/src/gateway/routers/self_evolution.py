"""Self-Evolution governance gateway router.

Exposes the full proposal lifecycle — create, shadow run, validate,
approve/reject, promote, rollback — over HTTP for operator tooling.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from src.self_evolution import (
    ChangeType,
    ProposalStatus,
    get_self_evolution_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/evolution", tags=["self_evolution"])
EvolutionExportDataset = str
EvolutionExportFormat = str


# ── Request / Response models ─────────────────────────────────────────────────

class ProposalResponse(BaseModel):
    proposal_id: str
    change_type: str
    title: str
    description: str
    proposed_change: dict[str, Any] = Field(default_factory=dict)
    current_value: dict[str, Any] = Field(default_factory=dict)
    source: str
    status: str
    created_at: float
    updated_at: float
    shadow_metrics: dict[str, Any] = Field(default_factory=dict)
    validation_notes: str
    approved_by: str | None = None
    approved_at: float | None = None
    promoted_at: float | None = None
    rejection_reason: str
    rollback_reason: str
    tags: list[str] = Field(default_factory=list)


class ProposalsListResponse(BaseModel):
    proposals: list[ProposalResponse] = Field(default_factory=list)
    total: int = 0


class CreateProposalRequest(BaseModel):
    change_type: ChangeType
    title: str
    description: str
    proposed_change: dict[str, Any] = Field(default_factory=dict)
    current_value: dict[str, Any] = Field(default_factory=dict)
    source: str = "operator"
    tags: list[str] = Field(default_factory=list)


class ApproveRequest(BaseModel):
    approved_by: str = "operator"


class RejectRequest(BaseModel):
    reason: str = ""
    rejected_by: str = "operator"


class RollbackRequest(BaseModel):
    reason: str = ""


class ValidationResponse(BaseModel):
    proposal_id: str
    passed: bool
    notes: str


class ShadowRunResponse(BaseModel):
    run_id: str
    proposal_id: str
    success: bool
    metrics: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    completed_at: float | None = None


class AuditTrailEntryResponse(BaseModel):
    entry_id: str
    proposal_id: str
    action: str
    timestamp: float
    actor: str
    from_status: str | None = None
    to_status: str | None = None
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditTrailListResponse(BaseModel):
    entries: list[AuditTrailEntryResponse] = Field(default_factory=list)
    total: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_response(p) -> ProposalResponse:
    return ProposalResponse(
        proposal_id=p.proposal_id,
        change_type=p.change_type,
        title=p.title,
        description=p.description,
        proposed_change=p.proposed_change,
        current_value=p.current_value,
        source=p.source,
        status=p.status.value if hasattr(p.status, "value") else str(p.status),
        created_at=p.created_at,
        updated_at=p.updated_at,
        shadow_metrics=p.shadow_metrics,
        validation_notes=p.validation_notes,
        approved_by=p.approved_by,
        approved_at=p.approved_at,
        promoted_at=p.promoted_at,
        rejection_reason=p.rejection_reason,
        rollback_reason=p.rollback_reason,
        tags=p.tags,
    )


def _attachment_headers(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def _raise_proposal_lifecycle_error(exc: ValueError) -> None:
    detail = str(exc)
    status_code = 404 if "not found" in detail.lower() else 400
    raise HTTPException(status_code=status_code, detail=detail) from exc


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/proposals", response_model=ProposalsListResponse)
async def list_proposals(
    status: str | None = Query(default=None),
    change_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> ProposalsListResponse:
    """List evolution proposals with optional filters."""
    svc = get_self_evolution_service()
    status_enum = None
    if status:
        try:
            status_enum = ProposalStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status!r}")
    proposals = svc.list_proposals(status=status_enum, change_type=change_type, limit=limit)
    return ProposalsListResponse(proposals=[_to_response(p) for p in proposals], total=len(proposals))


@router.post("/proposals", response_model=ProposalResponse, status_code=201)
async def create_proposal(request: CreateProposalRequest) -> ProposalResponse:
    """Create a new evolution proposal."""
    svc = get_self_evolution_service()
    p = svc.create_proposal(
        change_type=request.change_type,
        title=request.title,
        description=request.description,
        proposed_change=request.proposed_change,
        current_value=request.current_value,
        source=request.source,
        tags=request.tags,
    )
    return _to_response(p)


@router.get("/proposals/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(proposal_id: str) -> ProposalResponse:
    p = get_self_evolution_service().get_proposal(proposal_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")
    return _to_response(p)


@router.post("/proposals/{proposal_id}/shadow-run", response_model=ShadowRunResponse)
async def start_shadow_run(proposal_id: str) -> ShadowRunResponse:
    """Start a shadow evaluation run for the proposal."""
    svc = get_self_evolution_service()
    try:
        result = await svc.start_shadow_run(proposal_id)
    except ValueError as exc:
        _raise_proposal_lifecycle_error(exc)
    return ShadowRunResponse(
        run_id=result.run_id,
        proposal_id=result.proposal_id,
        success=result.success,
        metrics=result.metrics,
        errors=result.errors,
        completed_at=result.completed_at,
    )


@router.post("/proposals/{proposal_id}/validate", response_model=ValidationResponse)
async def validate_proposal(proposal_id: str) -> ValidationResponse:
    """Run quality-gate validation on a shadow-completed proposal."""
    svc = get_self_evolution_service()
    if svc.get_proposal(proposal_id) is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")
    passed, notes = svc.validate(proposal_id)
    return ValidationResponse(proposal_id=proposal_id, passed=passed, notes=notes)


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalResponse)
async def approve_proposal(proposal_id: str, request: ApproveRequest) -> ProposalResponse:
    """Operator approves a validated proposal for promotion."""
    svc = get_self_evolution_service()
    try:
        p = svc.approve(proposal_id, approved_by=request.approved_by)
    except ValueError as exc:
        _raise_proposal_lifecycle_error(exc)
    return _to_response(p)


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalResponse)
async def reject_proposal(proposal_id: str, request: RejectRequest) -> ProposalResponse:
    """Operator rejects a proposal."""
    svc = get_self_evolution_service()
    try:
        p = svc.reject(proposal_id, reason=request.reason, rejected_by=request.rejected_by)
    except ValueError as exc:
        _raise_proposal_lifecycle_error(exc)
    return _to_response(p)


@router.post("/proposals/{proposal_id}/promote", response_model=ProposalResponse)
async def promote_proposal(proposal_id: str) -> ProposalResponse:
    """Promote an approved proposal to the live system."""
    svc = get_self_evolution_service()
    try:
        p = await svc.promote(proposal_id)
    except ValueError as exc:
        _raise_proposal_lifecycle_error(exc)
    return _to_response(p)


@router.post("/proposals/{proposal_id}/rollback", response_model=ProposalResponse)
async def rollback_proposal(proposal_id: str, request: RollbackRequest) -> ProposalResponse:
    """Roll back a promoted proposal."""
    svc = get_self_evolution_service()
    try:
        p = svc.rollback(proposal_id, reason=request.reason)
    except ValueError as exc:
        _raise_proposal_lifecycle_error(exc)
    return _to_response(p)


@router.get("/audit", response_model=AuditTrailListResponse)
async def list_evolution_audit(
    proposal_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> AuditTrailListResponse:
    """List recent self-evolution audit trail entries."""
    svc = get_self_evolution_service()
    entries = svc.list_audit_trail(proposal_id=proposal_id, limit=limit)
    return AuditTrailListResponse(
        entries=[
            AuditTrailEntryResponse(
                entry_id=entry.entry_id,
                proposal_id=entry.proposal_id,
                action=entry.action,
                timestamp=entry.timestamp,
                actor=entry.actor,
                from_status=entry.from_status,
                to_status=entry.to_status,
                notes=entry.notes,
                metadata=entry.metadata,
            )
            for entry in entries
        ],
        total=len(entries),
    )


@router.get("/export", response_class=PlainTextResponse)
async def export_evolution_dataset(
    dataset: str = Query(default="audit", pattern="^(proposals|audit|shadow_runs)$"),
    format: str = Query(default="jsonl", pattern="^(jsonl|csv)$"),
) -> PlainTextResponse:
    """Export proposals, audit trail, or shadow runs for operator review."""
    svc = get_self_evolution_service()
    content = svc.export_dataset(dataset=dataset, format=format)
    media_type = "text/csv" if format == "csv" else "application/x-ndjson"
    filename = f"self-evolution-{dataset}.{format}"
    return PlainTextResponse(content=content, media_type=media_type, headers=_attachment_headers(filename))
