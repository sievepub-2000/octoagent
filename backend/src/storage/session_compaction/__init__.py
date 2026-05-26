"""Session compaction — inspired by claw-code's runtime compaction.

Provides context compression for long-running conversations to reduce token
usage while preserving key information.
"""

from src.storage.session_compaction.compactor import CompactionConfig, SessionCompactor

__all__ = ["SessionCompactor", "CompactionConfig"]
