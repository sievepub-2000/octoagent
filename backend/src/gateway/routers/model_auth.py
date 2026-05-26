"""Gateway router for model provider authentication."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.governance.model_auth.service import get_model_auth_service

router = APIRouter(prefix="/api/model-auth", tags=["model-auth"])


class ProviderAuthorizeRequest(BaseModel):
    api_key: str | None = Field(default=None)
    account_label: str | None = None
    base_url: str | None = None
    model: str | None = None
    auth_mode: str = "api_key"
    session_payload: dict[str, Any] | None = None
    sync_model: bool = False


class ProviderOAuthStartRequest(BaseModel):
    callback_url: str | None = None
    state: str | None = None
    prefer_web_dialog: bool = False


class ProviderOAuthCompleteRequest(BaseModel):
    model: str
    account_label: str | None = None
    set_default: bool = True
    state: str | None = None


class ProviderOAuthSessionRequest(BaseModel):
    state: str | None = None


@router.get("/templates")
async def get_model_auth_templates() -> dict[str, Any]:
    service = get_model_auth_service()
    return {"templates": service.templates()}


@router.get("/status")
async def get_model_auth_status() -> dict[str, Any]:
    service = get_model_auth_service()
    return {"providers": service.status()}


@router.post("/{provider_id}/authorize")
async def authorize_provider(provider_id: str, request: ProviderAuthorizeRequest) -> dict[str, Any]:
    service = get_model_auth_service()
    try:
        status = service.save_credentials(
            provider_id,
            api_key=request.api_key,
            account_label=request.account_label,
            base_url=request.base_url,
            model=request.model,
            auth_mode=request.auth_mode,
            session_payload=request.session_payload,
        )
        synced_model = service.sync_model_config(provider_id)["model"] if request.sync_model else None
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "provider": status, "model": synced_model}


@router.post("/{provider_id}/oauth/start")
async def start_provider_oauth(provider_id: str, request: ProviderOAuthStartRequest) -> dict[str, Any]:
    service = get_model_auth_service()
    try:
        return service.begin_oauth_login(
            provider_id,
            callback_url=request.callback_url,
            state=request.state,
            prefer_web_dialog=request.prefer_web_dialog,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{provider_id}/oauth/confirm")
async def confirm_provider_oauth(provider_id: str, request: ProviderOAuthSessionRequest) -> dict[str, Any]:
    if not request.state:
        raise HTTPException(status_code=400, detail="OAuth state is required")
    service = get_model_auth_service()
    try:
        return service.confirm_oauth_login(provider_id, state=request.state)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{provider_id}/oauth/callback", response_class=HTMLResponse)
async def provider_oauth_callback(provider_id: str, code: str | None = None, state: str | None = None, error: str | None = None) -> str:
    if error:
        return f"<html><body><h3>OAuth failed</h3><p>{error}</p></body></html>"
    if not code or not state:
        raise HTTPException(status_code=400, detail="OAuth code and state are required")
    service = get_model_auth_service()
    try:
        result = await service.complete_oauth_callback(provider_id, code=code, state=state)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    message = result.get("message") or "OAuth completed. You can return to OctoAgent."
    return f"<html><body><h3>OAuth completed</h3><p>{message}</p><script>window.close();</script></body></html>"


@router.post("/{provider_id}/oauth/models")
async def list_provider_oauth_models(provider_id: str, request: ProviderOAuthSessionRequest | None = None) -> dict[str, Any]:
    service = get_model_auth_service()
    try:
        return await service.discover_conversation_models(provider_id, state=request.state if request else None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{provider_id}/oauth/complete")
async def complete_provider_oauth(provider_id: str, request: ProviderOAuthCompleteRequest) -> dict[str, Any]:
    service = get_model_auth_service()
    try:
        return await service.configure_conversation_model(
            provider_id,
            model=request.model,
            account_label=request.account_label,
            set_default=request.set_default,
            state=request.state,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{provider_id}/logout")
async def logout_provider(provider_id: str) -> dict[str, Any]:
    service = get_model_auth_service()
    try:
        status = service.logout(provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "provider": status}


@router.post("/{provider_id}/test")
async def test_provider(provider_id: str) -> dict[str, Any]:
    service = get_model_auth_service()
    try:
        return await service.test_connection(provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{provider_id}/sync-model")
async def sync_provider_model(provider_id: str) -> dict[str, Any]:
    service = get_model_auth_service()
    try:
        return {"success": True, **service.sync_model_config(provider_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
