"""Configuration for external integration ingress and auth surfaces."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SystemPermissionScope = Literal["shell", "filesystem", "browser", "desktop", "runtime"]
SystemPermissionEffect = Literal["allow", "ask", "deny"]


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


class SystemExecutionPermissionRuleConfig(BaseModel):
    rule_id: str
    scope: SystemPermissionScope
    effect: SystemPermissionEffect
    match_prefixes: list[str] = Field(default_factory=list)
    match_values: list[str] = Field(default_factory=list)
    note: str | None = None


def _default_system_execution_rules() -> list[SystemExecutionPermissionRuleConfig]:
    return [
        SystemExecutionPermissionRuleConfig(
            rule_id="allow-safe-read",
            scope="shell",
            effect="allow",
            match_prefixes=[
                "pwd",
                "ls",
                "rg",
                "cat",
                "find",
                "git status",
                "git diff --stat",
                "uname",
                "whoami",
                "id",
                "env",
                "printenv",
                "which",
                "command -v",
                "python --version",
                "python3 --version",
                "go version",
                "go env",
                "node -v",
                "npm -v",
                "pnpm -v",
            ],
            note="Read-only inspection commands are auto-allowed.",
        ),
        SystemExecutionPermissionRuleConfig(
            rule_id="allow-workspace-paths",
            scope="filesystem",
            effect="allow",
            match_values=["/workspace", "/tmp"],
            note="Workspace-local read/write paths are allowed under repo policy.",
        ),
        SystemExecutionPermissionRuleConfig(
            rule_id="ask-browser-write",
            scope="browser",
            effect="ask",
            match_prefixes=["click", "fill", "submit", "eval"],
            note="Browser side effects require approval unless an upstream gate has cleared them.",
        ),
        SystemExecutionPermissionRuleConfig(
            rule_id="deny-destructive-shell",
            scope="shell",
            effect="deny",
            match_prefixes=["rm -rf", "git reset --hard", "mkfs", "shutdown"],
            note="Destructive shell commands are blocked.",
        ),
    ]


class SystemExecutionPermissionPolicyConfig(BaseModel):
    policy_id: str = Field(default="octoagent-system-default")
    title: str = Field(default="OctoAgent System Execution Default Policy")
    default_effect: SystemPermissionEffect = Field(default="ask")
    rules: list[SystemExecutionPermissionRuleConfig] = Field(default_factory=_default_system_execution_rules)


class SystemExecutionConfig(BaseModel):
    enabled: bool = Field(default=True)
    engine: Literal["none", "sandbox_exec", "desktop_agent", "hybrid"] = Field(default="sandbox_exec")
    supports_desktop_control: bool = Field(default=False)
    supports_window_introspection: bool = Field(default=False)
    supports_file_open_handoffs: bool = Field(default=True)
    system_cli_enabled: bool = Field(default=True)
    permission_policy: SystemExecutionPermissionPolicyConfig = Field(default_factory=SystemExecutionPermissionPolicyConfig)
    note: str = Field(default=("System-level operation is available through sandbox execution and system-execution planning APIs. Desktop-native control remains a scaffold and still requires an explicit desktop provider."))


class IntegrationsConfig(BaseModel):
    webhook: WebhookIngressConfig = Field(default_factory=WebhookIngressConfig)
    api: ApiIngressConfig = Field(default_factory=ApiIngressConfig)
    email: EmailIngressConfig = Field(default_factory=EmailIngressConfig)
    browser: BrowserAutomationConfig = Field(default_factory=BrowserAutomationConfig)
    system_execution: SystemExecutionConfig = Field(default_factory=SystemExecutionConfig)


_integrations_config = IntegrationsConfig()


def get_integrations_config() -> IntegrationsConfig:
    return _integrations_config


def load_integrations_config_from_dict(config_dict: dict) -> None:
    global _integrations_config
    _integrations_config = IntegrationsConfig(**config_dict)
