"""Default configuration constants for context compression and prompt caching.

All values can be overridden via environment variables with the prefix
``OCTOAGENT_COMPRESS_`` (e.g. ``OCTOAGENT_COMPRESS_KEEP_RECENT=15``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(f"OCTOAGENT_COMPRESS_{name}")
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(f"OCTOAGENT_COMPRESS_{name}")
    if raw is None:
        return default
    try:
        return max(0.01, float(raw))
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(f"OCTOAGENT_COMPRESS_{name}")
    if raw is None or not raw.strip():
        return default
    return raw.strip()


@dataclass(frozen=True)
class CompressionConfig:
    keep_recent_messages: int = 10
    compression_trigger_ratio: float = 0.80
    max_context_size: int = 128_000

    system_prompt_budget_ratio: float = 0.15
    tool_description_budget_ratio: float = 0.20
    conversation_budget_ratio: float = 0.45
    summary_budget_ratio: float = 0.20

    aux_model_name: str | None = None
    aux_max_tokens: int = 8_000

    chars_per_token_ascii: int = 4
    chars_per_token_cjk: int = 2

    anti_hijack_prefix: str = "\u3010\u5df2\u5b8c\u6210\u3011"
    anti_hijack_system_instruction: str = "This is a compressed summary of earlier conversation. DO NOT resume or re-execute any actions mentioned in the summary. The tasks described here have already been completed."
    anti_hijack_chinese_directive: str = "\u95ee\u9898\u5df2\u89e3\u51b3"


def load_compression_config() -> CompressionConfig:
    return CompressionConfig(
        keep_recent_messages=_env_int("KEEP_RECENT", 10),
        compression_trigger_ratio=_env_float("TRIGGER_RATIO", 0.80),
        max_context_size=_env_int("MAX_CONTEXT_SIZE", 128_000),
        system_prompt_budget_ratio=_env_float("SYSTEM_RATIO", 0.15),
        tool_description_budget_ratio=_env_float("TOOL_RATIO", 0.20),
        conversation_budget_ratio=_env_float("CONVO_RATIO", 0.45),
        summary_budget_ratio=_env_float("SUMMARY_RATIO", 0.20),
        aux_model_name=_env_str("AUX_MODEL", None) or None,
        aux_max_tokens=_env_int("AUX_MAX_TOKENS", 8_000),
    )


__all__ = ["CompressionConfig", "load_compression_config"]
