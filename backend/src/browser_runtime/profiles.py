"""Capability and provider profile helpers for browser runtime."""

from __future__ import annotations

from .contracts import BrowserProviderProfile, BrowserRuntimeCapability


class BrowserRuntimeProfileCatalog:
    """Expose stable browser runtime capability metadata."""

    def get_capability(self) -> BrowserRuntimeCapability:
        return BrowserRuntimeCapability()

    def list_provider_profiles(self) -> list[BrowserProviderProfile]:
        return [
            BrowserProviderProfile(
                provider_id="agent_browser",
                display_name="Agent Browser CLI",
                launch_mode="cli",
                default_session_type="ephemeral",
                supports_accessibility_snapshot=True,
                supports_batch_commands=True,
                supports_streaming=True,
                recommended_for_default_use=True,
            )
        ]
