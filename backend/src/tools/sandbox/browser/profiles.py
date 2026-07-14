"""Capability and provider profile helpers for browser runtime."""

from __future__ import annotations

from src.runtime.config.integrations_config import get_integrations_config

from .contracts import BrowserProviderProfile, BrowserRuntimeCapability


class BrowserRuntimeProfileCatalog:
    """Expose stable browser runtime capability metadata."""

    def get_capability(self) -> BrowserRuntimeCapability:
        config = get_integrations_config().browser
        return BrowserRuntimeCapability(
            enabled=config.enabled,
            embedded_engine=config.engine,
            executable_path=config.executable_path,
            supports_authenticated_sessions=config.supports_authenticated_sessions,
            note=config.note,
        )

    def list_provider_profiles(self) -> list[BrowserProviderProfile]:
        return [
            BrowserProviderProfile(
                provider_id="agent_browser",
                display_name="Agent Browser Headless",
                launch_mode="cli",
                default_session_type="ephemeral",
                supports_accessibility_snapshot=True,
                supports_batch_commands=True,
                supports_streaming=True,
                recommended_for_default_use=True,
            ),
            BrowserProviderProfile(
                provider_id="patchright_headless",
                display_name="Patchright Headless Browser",
                launch_mode="cli",
                default_session_type="ephemeral",
                supports_accessibility_snapshot=True,
                supports_batch_commands=True,
                supports_streaming=False,
                recommended_for_default_use=get_integrations_config().browser.engine == "patchright",
            ),
        ]
