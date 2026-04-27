"""Gateway router for external integration ingress capabilities."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.config.integrations_config import get_integrations_config

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


class IntegrationSurfaceResponse(BaseModel):
    enabled: bool
    auth_methods: list[str] = Field(default_factory=list)


class BrowserAutomationResponse(BaseModel):
    enabled: bool
    engine: str
    embedded_headless: bool
    supports_authenticated_sessions: bool
    supports_remote_browser_pool: bool
    note: str


class SystemExecutionResponse(BaseModel):
    enabled: bool
    engine: str
    supports_desktop_control: bool
    supports_window_introspection: bool
    supports_file_open_handoffs: bool
    note: str


class IntegrationCapabilitiesResponse(BaseModel):
    webhook: IntegrationSurfaceResponse
    api: IntegrationSurfaceResponse
    email: IntegrationSurfaceResponse
    browser: BrowserAutomationResponse
    system_execution: SystemExecutionResponse
    shared_ui_panel: bool = True
    tool_invocation_enabled: bool = True
    supported_identity_primitives: list[str] = Field(default_factory=list)


@router.get(
    "/capabilities",
    response_model=IntegrationCapabilitiesResponse,
    summary="Get Integration Capabilities",
    description="Expose the configured external ingress, auth, email, and browser-automation capability surface.",
)
async def get_integration_capabilities() -> IntegrationCapabilitiesResponse:
    config = get_integrations_config()
    return IntegrationCapabilitiesResponse(
        webhook=IntegrationSurfaceResponse(
            enabled=config.webhook.enabled,
            auth_methods=config.webhook.auth_methods,
        ),
        api=IntegrationSurfaceResponse(
            enabled=config.api.enabled,
            auth_methods=config.api.auth_methods,
        ),
        email=IntegrationSurfaceResponse(
            enabled=config.email.enabled,
            auth_methods=config.email.auth_methods,
        ),
        browser=BrowserAutomationResponse(
            enabled=config.browser.enabled,
            engine=config.browser.engine,
            embedded_headless=config.browser.embedded_headless,
            supports_authenticated_sessions=config.browser.supports_authenticated_sessions,
            supports_remote_browser_pool=config.browser.supports_remote_browser_pool,
            note=config.browser.note,
        ),
        system_execution=SystemExecutionResponse(
            enabled=config.system_execution.enabled,
            engine=config.system_execution.engine,
            supports_desktop_control=config.system_execution.supports_desktop_control,
            supports_window_introspection=config.system_execution.supports_window_introspection,
            supports_file_open_handoffs=config.system_execution.supports_file_open_handoffs,
            note=config.system_execution.note,
        ),
        shared_ui_panel=True,
        tool_invocation_enabled=True,
        supported_identity_primitives=[
            "oauth2",
            "api_key",
            "bearer_token",
            "hmac_signature",
            "email_basic_auth",
        ],
    )
