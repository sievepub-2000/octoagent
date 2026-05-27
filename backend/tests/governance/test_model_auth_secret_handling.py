"""Security-sensitive invariants for governance.model_auth.

These checks lock the operator-credential layer's surface area so that
regressions which would weaken multi-tenant secret handling fail fast in CI:

* Provider templates are immutable (frozen dataclass) — a contributor cannot
  silently mutate `env_var` or `default_base_url` at import time.
* All template env-var names follow the OCTOAGENT_MODEL_AUTH_<PROVIDER>
  convention so that operator audits can grep a single prefix.
* The public projection (`to_public_dict`) does NOT include OAuth client
  secret env names — protecting against accidental UI leakage.
* Importing the service module does not trigger a key-derivation side
  effect (it must only allocate state on first `get_model_auth_service()`).
"""

from __future__ import annotations

import dataclasses

import pytest

from src.governance.model_auth.service import (
    PROVIDER_TEMPLATES,
)


def test_provider_template_is_frozen():
    template = next(iter(PROVIDER_TEMPLATES.values()))
    assert dataclasses.is_dataclass(template)
    # frozen=True means attempting to mutate must raise FrozenInstanceError
    with pytest.raises(dataclasses.FrozenInstanceError):
        template.env_var = "OCTOAGENT_MODEL_AUTH_HIJACKED"  # type: ignore[misc]


def test_provider_templates_share_env_var_namespace():
    """All built-in providers must use the OCTOAGENT_MODEL_AUTH_* namespace.

    Operators audit credential exposure by grepping a single prefix; a stray
    template that wrote to `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` would
    leak into the global environment shared with unrelated tools.
    """
    bad = {
        pid: template.env_var
        for pid, template in PROVIDER_TEMPLATES.items()
        if not template.env_var.startswith("OCTOAGENT_MODEL_AUTH_")
    }
    assert bad == {}, f"providers must use OCTOAGENT_MODEL_AUTH_* env vars: {bad}"


def test_public_dict_omits_oauth_client_secrets():
    """`to_public_dict()` is the UI projection; it must never carry the
    *client secret* env var name (leaking that name is not a secret leak
    by itself, but it is a fingerprint of which secret the server has and
    invites credential-stuffing). The login URL/OAuth scopes are public."""
    for template in PROVIDER_TEMPLATES.values():
        public = template.to_public_dict()
        assert "oauth_client_secret_env" not in public
        assert "oauth_client_id_env" not in public
        assert "oauth_scopes" not in public


def test_provider_template_env_var_is_unique():
    """Two templates writing to the same env var would clobber each
    other's secrets at runtime."""
    env_vars = [t.env_var for t in PROVIDER_TEMPLATES.values()]
    assert len(env_vars) == len(set(env_vars)), (
        f"duplicate env_var across providers: {env_vars}"
    )


def test_service_import_has_no_filesystem_side_effects(tmp_path, monkeypatch):
    """Importing service module must not touch the filesystem."""
    import importlib
    import sys

    # Force re-import to observe import-time side effects.
    sys.modules.pop("src.governance.model_auth.service", None)

    monkeypatch.setenv("HOME", str(tmp_path))
    module = importlib.import_module("src.governance.model_auth.service")

    # No file created under HOME just by importing.
    assert list(tmp_path.iterdir()) == []
    assert hasattr(module, "ModelAuthService")
    assert hasattr(module, "get_model_auth_service")
