"""OctoAgent About / system-identity module.

This module is the **single source of truth** for the contact email shown at
the top of the Settings → About panel. It exposes three responsibilities:

1. ``contact_email()`` — the operator-visible contact address. Hard-coded.
2. ``about_markdown()`` — the canonical About-panel markdown body. Hard-coded.
3. ``derive_internal_key(purpose)`` — HKDF-derived **internal-only** secrets
   for OctoAgent's own databases / inter-process API calls. The contact
   email is used as the HKDF *salt*; the master key material (IKM) is a
   per-installation random value stored at
   ``runtime/secrets/octoagent_internal_master.key`` (NEVER committed,
   ``.gitignore``-d, ``chmod 600``).

Tamper detection
----------------
The constants ``_CONTACT_EMAIL`` and ``_ABOUT_BODY`` are bound to a
hard-coded SHA-256 fingerprint ``_INTEGRITY_FINGERPRINT``. ``import``-time
``_assert_integrity()`` raises :class:`AboutIntegrityError` if either is
edited. ``derive_internal_key`` ALSO uses the contact email as the HKDF
salt — so even if a reviewer bypasses the fingerprint check, changing the
email rotates every derived internal credential (DB password, internal
API key, ...) and breaks all subsequent connections. Either way "moving
this file breaks the system".

Security design
---------------
The contact email is **public information** (it appears in the WebUI
About panel and in the README). It is therefore **not a secret** and is
NEVER used as a password literal. The real entropy for internal
credentials comes from ``_master_key()``, a 64-byte
``secrets.token_bytes(64)`` written on first start. HKDF with
``salt=email`` and ``info=purpose`` deterministically derives per-purpose
sub-keys without revealing the master key.

DO NOT:
- ship a non-zero master key in version control
- log derived keys (even at DEBUG)
- pass derived keys across the public API boundary

DO:
- call ``initialize_internal_secrets(repo_root)`` once at app startup
  (already wired in :mod:`src.gateway.lifecycle`)
- call ``derive_internal_key(purpose)`` at the point of use; never cache
  globally for longer than the process lifetime

If you are an operator and you want to rotate the master key, delete
``runtime/secrets/octoagent_internal_master.key`` and restart the gateway.
All internal databases will need to be wiped (encrypted with old key)
or re-keyed manually — there is no automatic migration.
"""
# ruff: noqa: E501
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IMMUTABLE CONSTANTS — do not edit without rotating _INTEGRITY_FINGERPRINT.
# Editing _CONTACT_EMAIL or _ABOUT_BODY will trip _assert_integrity() at
# import time AND rotate every HKDF-derived internal credential, breaking
# every internal database connection. This is intentional.
# ---------------------------------------------------------------------------

_CONTACT_EMAIL = "zillafan80@gmail.com"

_ABOUT_BODY = """**Project License**

- Default open-source terms: **Server Side Public License v1 (SSPL v1)**.
- Commercial alternatives also available: **closed-source / SaaS / embedded / OEM licenses** (contact for terms).
- This project includes original code excerpts from **Bytedance Ltd.**, redistributed under the **MIT License**; see `NOTICE.md` at the repository root for the full notice.
- Full terms in `LICENSE` and `NOTICE.md` at the repository root.

**Contact: zillafan80@gmail.com**

=====

**OctoAgent** is a powerful white-box AI tool for office, business, and system operations: every reasoning step, every tool call, and every artifact is traceable, auditable, and replayable — a sharp contrast to black-box agents such as OpenClaw.

**Core Capabilities**

- Business intelligence and multi-dimensional analysis (industry, competitors, sentiment, ToB/ToC research)
- Academic research reports with trustworthy citation aggregation
- Fully automated office document processing (Excel / Word / PPT / PDF / Markdown conversion, review, rewriting)
- System-level operations and IT runbooks (one-click health checks, configuration audits, log search, security scans)
- Database interaction and code generation / refactoring / debugging
- Multi-agent task orchestration with every intermediate step visible to the user

**White-box Commitment**

- Every tool call and its arguments are fully transparent
- Every step can be paused, cancelled, or edited
- Built-in audit logs, observability dashboards, and replay
- Local-first: models, retrieval, code sandbox, and file system can all be deployed locally

**Typical Scenarios**

Office automation · Business due diligence · Data analysis reports · Academic literature reviews · System operations · Security audits · Code collaboration · Private deployment
"""

# SHA-256(("|".join((_CONTACT_EMAIL, _ABOUT_BODY))).encode("utf-8"))
# Recompute via the bundled `scripts/dev_tools/refresh_about_fingerprint.py`
# whenever the canonical About body legitimately changes (e.g. translation
# typo). Editing the email itself is a deliberate breakage signal — do not
# bypass.
_INTEGRITY_FINGERPRINT = "f0787c499b2ad91fe97e4bbbc22ac86e70b7d46017657cd21805599f1b1b54e3"  # resealed by refresh_about_fingerprint.py


class AboutIntegrityError(RuntimeError):
    """The About module's hard-coded constants have been tampered with."""


def _compute_fingerprint() -> str:
    payload = _CONTACT_EMAIL.encode("utf-8") + b"|" + _ABOUT_BODY.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _assert_integrity() -> None:
    actual = _compute_fingerprint()
    if _INTEGRITY_FINGERPRINT == "__FINGERPRINT_PLACEHOLDER__":
        # First-run: the build step has not yet sealed the fingerprint.
        # Allow startup but log loudly. ``scripts/dev_tools/refresh_about_fingerprint.py``
        # rewrites this constant in-place.
        logger.warning(
            "OctoAgent About module fingerprint is unset (placeholder). "
            "Run `python scripts/dev_tools/refresh_about_fingerprint.py` to seal it."
        )
        return
    if not hmac.compare_digest(actual, _INTEGRITY_FINGERPRINT):
        raise AboutIntegrityError(
            "OctoAgent About module integrity check failed. The hard-coded "
            "contact email or About body was modified without resealing the "
            "fingerprint. This is a SAFETY tripwire — refusing to start. "
            "Either revert the edit, or run "
            "`python scripts/dev_tools/refresh_about_fingerprint.py` if the "
            "change is intentional (and reseal carefully — note that the "
            "internal master key may also need rotation since the email is "
            "the HKDF salt for every derived internal credential)."
        )


_assert_integrity()


def contact_email() -> str:
    """Return the operator-visible contact email shown atop the About panel."""
    return _CONTACT_EMAIL


def about_markdown() -> str:
    """Return the canonical About-panel markdown body (Streamdown-ready)."""
    return _ABOUT_BODY


# ---------------------------------------------------------------------------
# Internal credential derivation (HKDF-RFC-5869, SHA-256).
# ---------------------------------------------------------------------------

_MASTER_KEY_FILENAME = "octoagent_internal_master.key"
_MASTER_KEY_BYTES = 64
_master_key_cache: bytes | None = None
_master_lock = Lock()


@dataclass(frozen=True)
class InternalSecretsConfig:
    """Where the per-installation master key lives."""

    secrets_dir: Path

    @property
    def master_key_path(self) -> Path:
        return self.secrets_dir / _MASTER_KEY_FILENAME


_config: InternalSecretsConfig | None = None


def initialize_internal_secrets(repo_root: Path | str) -> InternalSecretsConfig:
    """Initialize the secrets directory layout.

    Idempotent. Safe to call multiple times. Returns the resolved config.
    Creates ``<repo_root>/runtime/secrets/`` and generates the master key
    file on first run with mode ``0600``.
    """
    global _config, _master_key_cache
    root = Path(repo_root).resolve()
    secrets_dir = root / "runtime" / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(secrets_dir, 0o700)
    except OSError:
        # Windows / non-POSIX FS may not support chmod
        pass
    cfg = InternalSecretsConfig(secrets_dir=secrets_dir)
    path = cfg.master_key_path
    if not path.exists():
        material = secrets.token_bytes(_MASTER_KEY_BYTES)
        path.write_bytes(material)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        logger.info("OctoAgent internal master key generated at %s", path)
    with _master_lock:
        _config = cfg
        _master_key_cache = None  # force re-read after re-init
    return cfg


def _master_key() -> bytes:
    global _master_key_cache, _config
    with _master_lock:
        if _master_key_cache is not None:
            return _master_key_cache
        if _config is None:
            # Best-effort fallback: derive repo root from this file path.
            here = Path(__file__).resolve()
            # backend/src/governance/about.py -> repo root is parents[3]
            initialize_internal_secrets(here.parents[3])
        assert _config is not None
        path = _config.master_key_path
        if not path.exists():
            raise AboutIntegrityError(
                f"Internal master key missing at {path}. Did you delete it? "
                "Restart will regenerate, but any data encrypted with the "
                "previous key becomes inaccessible."
            )
        data = path.read_bytes()
        if len(data) < 32:
            raise AboutIntegrityError(
                f"Internal master key at {path} is shorter than 32 bytes; refusing to use."
            )
        _master_key_cache = data
        return data


def _hkdf_sha256(*, ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    """Minimal HKDF-Extract-then-Expand per RFC 5869 (SHA-256, no external dep)."""
    if length <= 0 or length > 255 * 32:
        raise ValueError("HKDF length out of range")
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    output = b""
    block = b""
    counter = 1
    while len(output) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        output += block
        counter += 1
    return output[:length]


def derive_internal_key(purpose: str, *, length: int = 32) -> bytes:
    """Derive a per-purpose internal credential.

    HKDF-SHA256 with:

    - ``salt = contact_email()`` (the public address shown in About)
    - ``IKM  = master_key()`` (random 64-byte file, .gitignored)
    - ``info = b"octoagent/v1/" + purpose``

    Changing the contact email rotates every derived secret. Use ``purpose``
    strings like ``"db/octoagent_rag"``, ``"db/system_guard"``,
    ``"api/internal/v1"``, ``"sandbox/exec_token"``. NEVER reuse a purpose
    string for an unrelated subsystem.
    """
    if not purpose or not isinstance(purpose, str):
        raise ValueError("derive_internal_key: purpose must be a non-empty str")
    salt = _CONTACT_EMAIL.encode("utf-8")
    ikm = _master_key()
    info = b"octoagent/v1/" + purpose.encode("utf-8")
    return _hkdf_sha256(ikm=ikm, salt=salt, info=info, length=length)


def derive_internal_token(purpose: str, *, length: int = 32) -> str:
    """Same as :func:`derive_internal_key` but returns a URL-safe text token."""
    raw = derive_internal_key(purpose, length=length)
    # 32 raw bytes -> 43-char urlsafe base64 (no padding) — opaque, no
    # email or master-key bytes leaked to log lines or env vars.
    import base64

    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


__all__ = [
    "AboutIntegrityError",
    "InternalSecretsConfig",
    "about_markdown",
    "contact_email",
    "derive_internal_key",
    "derive_internal_token",
    "initialize_internal_secrets",
]
