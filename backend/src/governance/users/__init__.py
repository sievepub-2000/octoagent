"""User account, email verification, device trust, and tenant binding store."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import smtplib
import sqlite3
import time
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from src.governance.multi_tenant import TenantContext, get_tenant_registry
from src.runtime.config.paths import get_paths

logger = logging.getLogger(__name__)

CODE_TTL_SECONDS = 10 * 60
SESSION_TTL_SECONDS = 30 * 24 * 3600


def _now() -> int:
    return int(time.time())


def _db_path() -> Path:
    return get_paths().runtime_root / "octoagent_users.db"


def _hash_secret(value: str, *, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), bytes.fromhex(salt), 200_000)
    return salt, digest.hex()


def _verify_secret(value: str, salt: str, digest: str) -> bool:
    _, candidate = _hash_secret(value, salt=salt)
    return hmac.compare_digest(candidate, digest)


def _hash_device(device_fingerprint: str) -> str:
    return hashlib.sha256(device_fingerprint.strip().encode("utf-8")).hexdigest()


def _tenant_id_for(username: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in username.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part) or "user"
    return f"user-{cleaned[:48]}"


@dataclass
class AuthSession:
    session_token: str
    user_id: str
    username: str
    email: str
    tenant_id: str
    expires_at: int


class UserAccountStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL DEFAULT '',
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    tenant_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    last_login_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS verification_codes (
                    challenge_id TEXT PRIMARY KEY,
                    purpose TEXT NOT NULL,
                    username TEXT NOT NULL,
                    email TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    password_salt TEXT,
                    password_hash TEXT,
                    display_name TEXT NOT NULL DEFAULT '',
                    expires_at INTEGER NOT NULL,
                    consumed_at INTEGER,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trusted_devices (
                    device_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    fingerprint_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    UNIQUE(user_id, fingerprint_hash)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    device_id TEXT,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL
                );
                """
            )

    def _send_email_code(self, *, email: str, code: str, purpose: str) -> str:
        host = os.getenv("OCTO_SMTP_HOST", "").strip()
        if not host:
            logger.warning("Auth email code for %s purpose=%s code=%s; SMTP is not configured", email, purpose, code)
            return "logged"
        port = int(os.getenv("OCTO_SMTP_PORT", "587"))
        username = os.getenv("OCTO_SMTP_USERNAME", "").strip()
        password = os.getenv("OCTO_SMTP_PASSWORD", "")
        sender = os.getenv("OCTO_SMTP_FROM", username or f"octoagent@{host}")
        message = EmailMessage()
        message["Subject"] = "OctoAgent verification code"
        message["From"] = sender
        message["To"] = email
        message.set_content(f"Your OctoAgent verification code is {code}. It expires in 10 minutes.")
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if os.getenv("OCTO_SMTP_TLS", "1") != "0":
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return "smtp"

    def start_registration(self, *, username: str, password: str, email: str, display_name: str = "") -> dict[str, Any]:
        username = username.strip()
        email = email.strip().lower()
        if len(username) < 3 or len(username) > 64:
            raise ValueError("Username must be 3-64 characters")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        if "@" not in email or len(email) > 254:
            raise ValueError("Valid email is required")
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM users WHERE username=? OR email=?", (username, email)).fetchone():
                raise ValueError("Username or email already registered")
        code = f"{secrets.randbelow(100_000_000):08d}"
        salt, code_hash = _hash_secret(code)
        pw_salt, pw_hash = _hash_secret(password)
        challenge_id = f"reg-{secrets.token_urlsafe(24)}"
        expires_at = _now() + CODE_TTL_SECONDS
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO verification_codes(challenge_id,purpose,username,email,code_hash,password_salt,password_hash,display_name,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (challenge_id, "registration", username, email, f"{salt}:{code_hash}", pw_salt, pw_hash, display_name.strip(), expires_at, _now()),
            )
        delivery = self._send_email_code(email=email, code=code, purpose="registration")
        payload: dict[str, Any] = {"challenge_id": challenge_id, "expires_at": expires_at, "delivery": delivery}
        if os.getenv("OCTO_AUTH_DEV_EXPOSE_CODES") == "1":
            payload["dev_code"] = code
        return payload

    def _consume_code(self, *, challenge_id: str, code: str, purpose: str) -> sqlite3.Row:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM verification_codes WHERE challenge_id=? AND purpose=?", (challenge_id, purpose)).fetchone()
            if row is None or row["consumed_at"] is not None or row["expires_at"] < _now():
                raise ValueError("Verification code expired or not found")
            salt, digest = str(row["code_hash"]).split(":", 1)
            if not _verify_secret(code.strip(), salt, digest):
                raise ValueError("Invalid verification code")
            conn.execute("UPDATE verification_codes SET consumed_at=? WHERE challenge_id=?", (_now(), challenge_id))
            return row

    def verify_registration(self, *, challenge_id: str, code: str, device_fingerprint: str) -> AuthSession:
        row = self._consume_code(challenge_id=challenge_id, code=code, purpose="registration")
        user_id = f"user-{secrets.token_urlsafe(18)}"
        tenant_id = _tenant_id_for(row["username"])
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users(user_id,username,email,display_name,password_salt,password_hash,tenant_id,created_at,updated_at,last_login_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (user_id, row["username"], row["email"], row["display_name"], row["password_salt"], row["password_hash"], tenant_id, now, now, now),
            )
        self._ensure_tenant(tenant_id=tenant_id, username=row["username"], email=row["email"], display_name=row["display_name"])
        return self._create_session(user_id=user_id, device_fingerprint=device_fingerprint)

    def _ensure_tenant(self, *, tenant_id: str, username: str, email: str, display_name: str) -> None:
        reg = get_tenant_registry()
        tenant = reg.get_tenant(tenant_id)
        if tenant.tenant_id != "default" or tenant_id == "default":
            return
        reg.register(
            TenantContext(
                tenant_id=tenant_id,
                display_name=display_name or username,
                tier="pro",
                metadata={"user_account": username, "email": email},
            )
        )

    def _create_session(self, *, user_id: str, device_fingerprint: str) -> AuthSession:
        now = _now()
        fingerprint_hash = _hash_device(device_fingerprint)
        device_id = f"device-{secrets.token_urlsafe(18)}"
        token = f"octo_{secrets.token_urlsafe(32)}"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires_at = now + SESSION_TTL_SECONDS
        with self._connect() as conn:
            existing = conn.execute("SELECT device_id FROM trusted_devices WHERE user_id=? AND fingerprint_hash=?", (user_id, fingerprint_hash)).fetchone()
            if existing:
                device_id = existing["device_id"]
                conn.execute("UPDATE trusted_devices SET last_seen_at=? WHERE device_id=?", (now, device_id))
            else:
                conn.execute("INSERT INTO trusted_devices(device_id,user_id,fingerprint_hash,created_at,last_seen_at) VALUES(?,?,?,?,?)", (device_id, user_id, fingerprint_hash, now, now))
            conn.execute("INSERT INTO sessions(session_token_hash,user_id,device_id,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?,?)", (token_hash, user_id, device_id, now, expires_at, now))
            user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return AuthSession(token, user["user_id"], user["username"], user["email"], user["tenant_id"], expires_at)

    def login(self, *, username: str, password: str, device_fingerprint: str) -> AuthSession:
        with self._connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=? AND status='active'", (username.strip(),)).fetchone()
            if user is None or not _verify_secret(password, user["password_salt"], user["password_hash"]):
                raise ValueError("Invalid username or password")
            conn.execute("UPDATE users SET last_login_at=?, updated_at=? WHERE user_id=?", (_now(), _now(), user["user_id"]))
        return self._create_session(user_id=user["user_id"], device_fingerprint=device_fingerprint)

    def device_login(self, *, username: str, device_fingerprint: str) -> AuthSession:
        fingerprint_hash = _hash_device(device_fingerprint)
        with self._connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=? AND status='active'", (username.strip(),)).fetchone()
            if user is None:
                raise ValueError("Unknown user")
            device = conn.execute("SELECT 1 FROM trusted_devices WHERE user_id=? AND fingerprint_hash=?", (user["user_id"], fingerprint_hash)).fetchone()
            if device is None:
                raise PermissionError("Email verification required for this terminal")
        return self._create_session(user_id=user["user_id"], device_fingerprint=device_fingerprint)

    def start_device_verification(self, *, username: str) -> dict[str, Any]:
        with self._connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=? AND status='active'", (username.strip(),)).fetchone()
            if user is None:
                raise ValueError("Unknown user")
        code = f"{secrets.randbelow(100_000_000):08d}"
        salt, code_hash = _hash_secret(code)
        challenge_id = f"dev-{secrets.token_urlsafe(24)}"
        expires_at = _now() + CODE_TTL_SECONDS
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO verification_codes(challenge_id,purpose,username,email,code_hash,expires_at,created_at) VALUES(?,?,?,?,?,?,?)",
                (challenge_id, "device", user["username"], user["email"], f"{salt}:{code_hash}", expires_at, _now()),
            )
        delivery = self._send_email_code(email=user["email"], code=code, purpose="device")
        payload: dict[str, Any] = {"challenge_id": challenge_id, "expires_at": expires_at, "delivery": delivery}
        if os.getenv("OCTO_AUTH_DEV_EXPOSE_CODES") == "1":
            payload["dev_code"] = code
        return payload

    def verify_device(self, *, challenge_id: str, code: str, device_fingerprint: str) -> AuthSession:
        row = self._consume_code(challenge_id=challenge_id, code=code, purpose="device")
        with self._connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=? AND email=? AND status='active'", (row["username"], row["email"])).fetchone()
            if user is None:
                raise ValueError("Unknown user")
        return self._create_session(user_id=user["user_id"], device_fingerprint=device_fingerprint)

    def session_for_token(self, token: str) -> AuthSession | None:
        token_hash = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT s.*, u.user_id, u.username, u.email, u.tenant_id FROM sessions s JOIN users u ON u.user_id=s.user_id WHERE s.session_token_hash=? AND s.expires_at>=?",
                (token_hash, _now()),
            ).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE sessions SET last_seen_at=? WHERE session_token_hash=?", (_now(), token_hash))
        return AuthSession(token, row["user_id"], row["username"], row["email"], row["tenant_id"], row["expires_at"])


_store: UserAccountStore | None = None


def get_user_account_store() -> UserAccountStore:
    global _store
    if _store is None:
        _store = UserAccountStore()
    return _store
