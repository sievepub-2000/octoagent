"""Conservative repair for UTF-8 text accidentally decoded as Latin-1."""

from __future__ import annotations

_MOJIBAKE_MARKERS = frozenset("ÃÂâðåäæéçèï")


def _mojibake_score(text: str) -> int:
    controls = sum(1 for char in text if 0x80 <= ord(char) <= 0x9F)
    markers = sum(text.count(char) for char in _MOJIBAKE_MARKERS)
    replacement = text.count("�") * 4
    return controls * 3 + markers + replacement


def repair_mojibake(value: str) -> str:
    """Return a repaired value only when UTF-8 decoding clearly improves it."""
    current = str(value or "")
    for _ in range(2):
        try:
            candidate = current.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if _mojibake_score(candidate) >= _mojibake_score(current):
            break
        current = candidate
    return current


__all__ = ["repair_mojibake"]
