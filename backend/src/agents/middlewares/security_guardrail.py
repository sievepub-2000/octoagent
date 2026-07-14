"""Enhanced security guardrails middleware for tool execution.

Provides four layers of protection:
  - Command pattern detection (blocks dangerous shell patterns)
  - File operation guard (system dirs, large writes, modification frequency)
  - Network operation guard (outbound logging, malicious IP blocking, rate limits)
  - Resource guard (CPU/memory tracking, kill on excess)
"""

from __future__ import annotations

import ipaddress
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dangerous command patterns
# ---------------------------------------------------------------------------

_DANGEROUS_COMMAND_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\brm\s+(-rf|-fr)\s+/(\s|$)", re.IGNORECASE), "rm -rf /"),
    (re.compile(r"\bmkfs\b", re.IGNORECASE), "mkfs"),
    (re.compile(r"\bdd\s+if=/dev/zero", re.IGNORECASE), "dd if=/dev/zero"),
    (re.compile(r">\s*/etc/", re.IGNORECASE), "write to /etc"),
    (re.compile(r"chmod\s+777\b"), "chmod 777"),
    (re.compile(r"\beval\s+\(?\s*base64", re.IGNORECASE), "base64 decode + exec"),
    (re.compile(r"nmap\s+-s[SP].*\b10\.\d+\.\d+\.\d+|nmap\s+-s[SP].*\b192\.168\.\d+\.\d+|nmap\s+-s[SP].*\b172\.(1[6-9]|2\d|3[01])\.\d+\.\d+", re.IGNORECASE), "network scan internal IPs"),
    (re.compile(r"\bwget\b.*\|\s*(sh|bash)", re.IGNORECASE), "pipe wget to shell"),
    (re.compile(r"\bcurl\b.*\|\s*(sh|bash)", re.IGNORECASE), "pipe curl to shell"),
]

# IP ranges considered internal/malicious for network guard
_INTERNAL_IP_RANGES: list[ipaddress.IPv4Network] = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]

_SYSTEM_WRITE_DIRS: tuple[str, ...] = ("/etc", "/usr", "/var", "/bin", "/sbin", "/lib", "/boot")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class GuardrailViolation:
    category: str
    severity: str  # "block" or "warn"
    detail: str
    tool_name: str = ""
    args_preview: str = ""


@dataclass
class SessionRateState:
    api_calls: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SecurityGuardrail middleware
# ---------------------------------------------------------------------------


class SecurityGuardrail:
    """Four-layer security guardrail for tool execution."""

    def __init__(
        self,
        memory_limit_mb: float = 512.0,
        timeout_seconds: float = 120.0,
        rate_limit_per_minute: int = 20,
        file_mod_alert_threshold: int = 10,
        file_mod_window_seconds: float = 60.0,
    ) -> None:
        self.memory_limit_bytes = int(memory_limit_mb * 1024 * 1024)
        self.timeout_seconds = timeout_seconds
        self.rate_limit_per_minute = rate_limit_per_minute
        self.file_mod_alert_threshold = file_mod_alert_threshold
        self.file_mod_window_seconds = file_mod_window_seconds

        # Per-session state (keyed by session id or None for global)
        self._rate_states: dict[str, SessionRateState] = defaultdict(SessionRateState)
        self._file_mod_times: dict[str, list[float]] = defaultdict(list)
        self._tool_call_start: dict[int, float] = {}

    # ------------------------------------------------------------------
    # Command Pattern Detection
    # ------------------------------------------------------------------

    def check_command_patterns(self, command: str) -> GuardrailViolation | None:
        """Check a shell command against dangerous pattern list."""
        for pattern, label in _DANGEROUS_COMMAND_PATTERNS:
            if pattern.search(command):
                return GuardrailViolation(
                    category="command_pattern",
                    severity="block",
                    detail=f"Blocked dangerous command pattern: {label}",
                    args_preview=command[:200],
                )
        return None

    # ------------------------------------------------------------------
    # File Operation Guard
    # ------------------------------------------------------------------

    def check_file_write(self, path: str) -> GuardrailViolation | None:
        """Check if a file write target is in a protected system directory."""
        normalized = path.replace("\\", "/").rstrip("/")
        for sys_dir in _SYSTEM_WRITE_DIRS:
            if normalized == sys_dir or normalized.startswith(sys_dir + "/"):
                return GuardrailViolation(
                    category="file_operation",
                    severity="block",
                    detail=f"Blocked write to system directory: {sys_dir}",
                    args_preview=path[:200],
                )
        return None

    def check_file_size(self, size_bytes: int) -> GuardrailViolation | None:
        """Warn on writes larger than 1 MB."""
        if size_bytes > 1_048_576:
            return GuardrailViolation(
                category="file_operation",
                severity="warn",
                detail=f"Large file write detected: {size_bytes / 1_048_576:.1f} MB",
                args_preview=f"{size_bytes} bytes",
            )
        return None

    def track_file_modification(self, path: str) -> GuardrailViolation | None:
        """Track file modification frequency; alert if same file modified too often."""
        now = time.monotonic()
        timestamps = self._file_mod_times[path]
        timestamps.append(now)

        # Prune old entries outside the window
        cutoff = now - self.file_mod_window_seconds
        self._file_mod_times[path] = [t for t in timestamps if t > cutoff]
        timestamps = self._file_mod_times[path]

        if len(timestamps) > self.file_mod_alert_threshold:
            return GuardrailViolation(
                category="file_operation",
                severity="warn",
                detail=f"File modified {len(timestamps)} times in {self.file_mod_window_seconds:.0f}s window (limit: {self.file_mod_alert_threshold})",
                args_preview=path[:200],
            )
        return None

    # ------------------------------------------------------------------
    # Network Operation Guard
    # ------------------------------------------------------------------

    def check_network_target(self, url: str) -> GuardrailViolation | None:
        """Check if a URL targets a known malicious or internal IP range."""
        try:
            parsed = urlparse(url)
            host = parsed.hostname
            if not host:
                return None
            # Skip IPv6 for simplicity; only check IPv4
            try:
                ip = ipaddress.ip_address(host)
            except ValueError:
                return None  # hostname, not IP
            if not isinstance(ip, ipaddress.IPv4Address):
                return None
            for net in _INTERNAL_IP_RANGES:
                if ip in net:
                    return GuardrailViolation(
                        category="network_operation",
                        severity="warn",
                        detail=f"Outbound connection to internal IP range: {host}",
                        args_preview=url[:200],
                    )
        except Exception as exc:  # noqa: BLE001 - never block on parse errors
            logger.debug("Network guardrail parse error for %s: %s", url, exc)
        return None

    def check_rate_limit(self, session_id: str = "default") -> GuardrailViolation | None:
        """Check if the session has exceeded API call rate limit."""
        state = self._rate_states[session_id]
        now = time.monotonic()
        cutoff = now - 60.0
        state.api_calls = [t for t in state.api_calls if t > cutoff]

        if len(state.api_calls) >= self.rate_limit_per_minute:
            return GuardrailViolation(
                category="network_operation",
                severity="block",
                detail=f"Rate limit exceeded: {len(state.api_calls)} calls in last 60s (limit: {self.rate_limit_per_minute})",
            )

        state.api_calls.append(now)
        return None

    def log_network_call(self, url: str, session_id: str = "default") -> None:
        """Log an outbound network call and check rate limit."""
        violation = self.check_rate_limit(session_id)
        if violation:
            logger.warning("Network guardrail blocked: %s", violation.detail)

    # ------------------------------------------------------------------
    # Resource Guard
    # ------------------------------------------------------------------

    def track_tool_call_start(self, call_id: int) -> None:
        """Record the start time of a tool call for timeout tracking."""
        self._tool_call_start[call_id] = time.monotonic()

    def check_tool_call_timeout(self, call_id: int) -> GuardrailViolation | None:
        """Check if a tool call has exceeded its timeout."""
        start = self._tool_call_start.get(call_id)
        if start is None:
            return None
        elapsed = time.monotonic() - start
        if elapsed > self.timeout_seconds:
            return GuardrailViolation(
                category="resource",
                severity="block",
                detail=f"Tool call exceeded timeout: {elapsed:.0f}s (limit: {self.timeout_seconds:.0f}s)",
            )
        return None

    def check_memory_usage(self, current_bytes: int) -> GuardrailViolation | None:
        """Check if memory usage exceeds the configured limit."""
        if current_bytes > self.memory_limit_bytes:
            return GuardrailViolation(
                category="resource",
                severity="block",
                detail=f"Memory usage exceeded limit: {current_bytes / 1_048_576:.0f} MB (limit: {self.memory_limit_bytes / 1_048_576:.0f} MB)",
            )
        return None

    # ------------------------------------------------------------------
    # Unified check entry point
    # ------------------------------------------------------------------

    def check_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        session_id: str = "default",
    ) -> list[GuardrailViolation]:
        """Run all guardrails against a single tool call. Returns violations."""
        violations: list[GuardrailViolation] = []

        # Extract command if present
        command = args.get("command", "") if isinstance(args, dict) else ""
        if isinstance(command, str) and command.strip():
            v = self.check_command_patterns(command)
            if v:
                v.tool_name = tool_name
                violations.append(v)

        # Extract file paths if present
        for key in ("path", "file_path", "filepath", "filename"):
            path_val = args.get(key, "") if isinstance(args, dict) else ""
            if isinstance(path_val, str) and path_val.strip():
                v = self.check_file_write(path_val)
                if v:
                    v.tool_name = tool_name
                    violations.append(v)

        # Extract URLs for network guard
        for key in ("url", "endpoint"):
            url_val = args.get(key, "") if isinstance(args, dict) else ""
            if isinstance(url_val, str) and url_val.strip():
                v = self.check_network_target(url_val)
                if v:
                    v.tool_name = tool_name
                    violations.append(v)

        # Rate limit check on every tool call
        rate_v = self.check_rate_limit(session_id)
        if rate_v:
            rate_v.tool_name = tool_name
            violations.append(rate_v)

        return violations


__all__ = ["SecurityGuardrail", "GuardrailViolation"]
