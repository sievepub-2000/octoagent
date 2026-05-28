"""OpenRouter request policy helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

_DEFAULT_APP_URL = "https://github.com/sievepub-2000/octoagent"
_DEFAULT_APP_TITLE = "OctoAgent"
_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in _FALSE_VALUES


def is_openrouter_base_url(base_url: str | None) -> bool:
    if not base_url:
        return False
    try:
        hostname = urlparse(base_url).hostname or ""
    except ValueError:
        return False
    hostname = hostname.lower()
    return hostname == "openrouter.ai" or hostname.endswith(".openrouter.ai")


def is_openrouter_model_config(model_config: Any) -> bool:
    provider_name = str(getattr(model_config, "provider_name", "") or "").strip().lower()
    if provider_name == "openrouter":
        return True
    return is_openrouter_base_url(str(getattr(model_config, "base_url", "") or ""))


def openrouter_app_attribution_headers() -> dict[str, str]:
    app_url = (os.getenv("OCTOAGENT_OPENROUTER_APP_URL") or os.getenv("OCTOAGENT_PUBLIC_BASE_URL") or _DEFAULT_APP_URL).strip()
    app_title = (os.getenv("OCTOAGENT_OPENROUTER_APP_TITLE") or _DEFAULT_APP_TITLE).strip()
    headers: dict[str, str] = {}
    if app_url:
        headers["HTTP-Referer"] = app_url
    if app_title:
        headers["X-Title"] = app_title
    return headers


def openrouter_usage_tracking_enabled() -> bool:
    return _env_bool("OCTOAGENT_OPENROUTER_USAGE_INCLUDE", default=True)


def _mapping_copy(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _has_header(headers: Mapping[str, Any], header_name: str) -> bool:
    expected = header_name.lower()
    return any(str(existing).lower() == expected for existing in headers)


def _merge_default_headers(
    model_settings_from_config: dict[str, Any],
    runtime_kwargs: dict[str, Any],
) -> None:
    merged = _mapping_copy(runtime_kwargs.pop("default_headers", None))
    merged.update(_mapping_copy(model_settings_from_config.pop("default_headers", None)))
    for header_name, header_value in openrouter_app_attribution_headers().items():
        if not _has_header(merged, header_name):
            merged[header_name] = header_value
    if merged:
        model_settings_from_config["default_headers"] = merged


def _merge_extra_body(
    model_settings_from_config: dict[str, Any],
    runtime_kwargs: dict[str, Any],
) -> None:
    merged = _mapping_copy(runtime_kwargs.pop("extra_body", None))
    merged.update(_mapping_copy(model_settings_from_config.pop("extra_body", None)))
    if openrouter_usage_tracking_enabled():
        usage = _mapping_copy(merged.get("usage"))
        usage["include"] = True
        merged["usage"] = usage
    if merged:
        model_settings_from_config["extra_body"] = merged


def apply_openrouter_request_options(
    *,
    model_settings_from_config: dict[str, Any],
    runtime_kwargs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    model_settings = dict(model_settings_from_config)
    kwargs = dict(runtime_kwargs)
    _merge_default_headers(model_settings, kwargs)
    _merge_extra_body(model_settings, kwargs)
    return model_settings, kwargs
