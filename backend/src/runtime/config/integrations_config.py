"""Configuration for external integration ingress and auth surfaces."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IngressAuthMethod = Literal[
    "none",
    "api_key",
    "bearer_token",
    "hmac_signature",
    "oauth2_client_credentials",
    "oauth2_authorization_code",
    "smtp_basic",
]


class WebhookIngressConfig(BaseModel):
    enabled: bool = Field(default=False)
    auth_methods: list[IngressAuthMethod] = Field(default_factory=lambda: ["hmac_signature", "bearer_token", "api_key"])
    supported_events: list[str] = Field(
        default_factory=lambda: [
            "task.created",
            "task.updated",
            "message.created",
            "incident.created",
        ]
    )
    require_timestamp_window_seconds: int = Field(default=300, ge=0)


class ApiIngressConfig(BaseModel):
    enabled: bool = Field(default=False)
    auth_methods: list[IngressAuthMethod] = Field(default_factory=lambda: ["bearer_token", "api_key", "oauth2_client_credentials"])
    supports_service_accounts: bool = Field(default=True)
    supports_per_client_rate_limits: bool = Field(default=True)


class EmailIngressConfig(BaseModel):
    enabled: bool = Field(default=False)
    auth_methods: list[IngressAuthMethod] = Field(default_factory=lambda: ["smtp_basic"])
    supports_inbound_parse: bool = Field(default=False)
    supports_outbound_delivery: bool = Field(default=False)


class BrowserAutomationConfig(BaseModel):
    enabled: bool = Field(default=False)
    engine: Literal["patchright", "playwright", "camoufox", "cloakbrowser", "remote_cdp", "none"] = Field(default="playwright")
    embedded_headless: bool = Field(default=True)
    headless: bool = Field(default=True)
    executable_path: str | None = Field(default=None)
    artifacts_dir: str | None = Field(default=None)
    supports_authenticated_sessions: bool = Field(default=False)
    supports_remote_browser_pool: bool = Field(default=False)
    note: str = Field(default=("Prefer Patchright/Playwright for the embedded headless provider. Camoufox/Cloakbrowser remain selectable when their runtime is installed and explicitly configured."))


class IntegrationsConfig(BaseModel):
    webhook: WebhookIngressConfig = Field(default_factory=WebhookIngressConfig)
    api: ApiIngressConfig = Field(default_factory=ApiIngressConfig)
    email: EmailIngressConfig = Field(default_factory=EmailIngressConfig)
    browser: BrowserAutomationConfig = Field(default_factory=BrowserAutomationConfig)


_integrations_config = IntegrationsConfig()


def get_integrations_config() -> IntegrationsConfig:
    return _integrations_config


def load_integrations_config_from_dict(config_dict: dict) -> None:
    global _integrations_config
    _integrations_config = IntegrationsConfig(**config_dict)
