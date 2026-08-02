"""User registration, email verification, login, and trusted-device auth."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.governance.users import AuthSession, get_user_account_store

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterStartRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    email: str = Field(min_length=3, max_length=254)
    display_name: str = ""

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Valid email is required")
        return normalized


class VerifyRequest(BaseModel):
    challenge_id: str
    code: str = Field(min_length=8, max_length=8)
    device_fingerprint: str = Field(min_length=16)


class LoginRequest(BaseModel):
    username: str
    password: str
    device_fingerprint: str = Field(min_length=16)


class DeviceLoginRequest(BaseModel):
    username: str
    device_fingerprint: str = Field(min_length=16)


class DeviceVerifyStartRequest(BaseModel):
    username: str


class AuthSessionResponse(BaseModel):
    session_token: str
    user_id: str
    username: str
    email: str
    tenant_id: str
    expires_at: int


class AuthChallengeResponse(BaseModel):
    challenge_id: str
    expires_at: int
    delivery: str
    dev_code: str | None = None


def _session_response(session: AuthSession) -> AuthSessionResponse:
    return AuthSessionResponse(**session.__dict__)


async def _store_call(method: str, **kwargs: Any) -> Any:
    """Keep the file-backed auth store off LangGraph's ASGI event loop."""

    return await asyncio.to_thread(
        lambda: getattr(get_user_account_store(), method)(**kwargs),
    )


@router.post("/register/start", response_model=AuthChallengeResponse)
async def start_registration(request: RegisterStartRequest) -> dict[str, Any]:
    try:
        return await _store_call("start_registration", **request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/register/verify", response_model=AuthSessionResponse)
async def verify_registration(request: VerifyRequest) -> AuthSessionResponse:
    try:
        return _session_response(await _store_call("verify_registration", **request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login", response_model=AuthSessionResponse)
async def login(request: LoginRequest) -> AuthSessionResponse:
    try:
        return _session_response(await _store_call("login", **request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/device-login", response_model=AuthSessionResponse)
async def device_login(request: DeviceLoginRequest) -> AuthSessionResponse:
    try:
        return _session_response(await _store_call("device_login", **request.model_dump()))
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/device/verify/start", response_model=AuthChallengeResponse)
async def start_device_verification(request: DeviceVerifyStartRequest) -> dict[str, Any]:
    try:
        return await _store_call("start_device_verification", username=request.username)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/device/verify", response_model=AuthSessionResponse)
async def verify_device(request: VerifyRequest) -> AuthSessionResponse:
    try:
        return _session_response(await _store_call("verify_device", **request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/me", response_model=AuthSessionResponse)
async def me(x_octoagent_session_token: str | None = Header(default=None, alias="X-OctoAgent-Session-Token")) -> AuthSessionResponse:
    session = await _store_call("session_for_token", token=x_octoagent_session_token or "")
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return _session_response(session)
