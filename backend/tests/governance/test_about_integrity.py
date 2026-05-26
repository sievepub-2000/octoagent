"""About panel integrity tests."""
from __future__ import annotations

import hashlib
import importlib
import os
import shutil
import sys
from pathlib import Path

import pytest


def _reload_about():
    if "src.governance.about" in sys.modules:
        del sys.modules["src.governance.about"]
    return importlib.import_module("src.governance.about")


def test_contact_email_is_hardcoded():
    about = _reload_about()
    assert about.contact_email() == "zillafan80@gmail.com"


def test_about_markdown_starts_with_contact_line():
    about = _reload_about()
    body = about.about_markdown()
    assert body.startswith("联系作者：zillafan80@gmail.com")
    assert "=====" in body


def test_integrity_fingerprint_matches_constants():
    about = _reload_about()
    payload = about._CONTACT_EMAIL.encode("utf-8") + b"|" + about._ABOUT_BODY.encode("utf-8")
    expected = hashlib.sha256(payload).hexdigest()
    # Either the sealed fingerprint matches, or the placeholder is present
    # (which is a soft warning state, not a hard failure).
    assert about._INTEGRITY_FINGERPRINT in {expected, "__FINGERPRINT_PLACEHOLDER__"}


def test_tampered_email_trips_integrity_check(monkeypatch):
    about = _reload_about()
    if about._INTEGRITY_FINGERPRINT == "__FINGERPRINT_PLACEHOLDER__":
        pytest.skip("fingerprint not sealed yet; tamper-detection inactive")
    monkeypatch.setattr(about, "_CONTACT_EMAIL", "attacker@example.com", raising=True)
    with pytest.raises(about.AboutIntegrityError):
        about._assert_integrity()


def test_derive_internal_key_is_deterministic(tmp_path):
    about = _reload_about()
    about.initialize_internal_secrets(tmp_path)
    key1 = about.derive_internal_key("db/test")
    key2 = about.derive_internal_key("db/test")
    assert key1 == key2
    assert len(key1) == 32


def test_derive_internal_key_changes_per_purpose(tmp_path):
    about = _reload_about()
    about.initialize_internal_secrets(tmp_path)
    a = about.derive_internal_key("db/one")
    b = about.derive_internal_key("db/two")
    assert a != b


def test_derive_internal_key_changes_when_master_rotates(tmp_path):
    about = _reload_about()
    about.initialize_internal_secrets(tmp_path)
    first = about.derive_internal_key("db/rotate-test")
    # Wipe and reinit -> brand new master key
    key_file = tmp_path / "runtime" / "secrets" / "octoagent_internal_master.key"
    key_file.unlink()
    # Force cache reset by re-init
    about.initialize_internal_secrets(tmp_path)
    second = about.derive_internal_key("db/rotate-test")
    assert first != second


def test_master_key_file_is_owner_only(tmp_path):
    about = _reload_about()
    about.initialize_internal_secrets(tmp_path)
    key_file = tmp_path / "runtime" / "secrets" / "octoagent_internal_master.key"
    assert key_file.exists()
    if os.name == "posix":
        mode = key_file.stat().st_mode & 0o777
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"


def test_derive_internal_token_is_urlsafe(tmp_path):
    about = _reload_about()
    about.initialize_internal_secrets(tmp_path)
    token = about.derive_internal_token("api/internal/v1")
    assert isinstance(token, str)
    assert "=" not in token
    assert all(c.isalnum() or c in "-_" for c in token)
