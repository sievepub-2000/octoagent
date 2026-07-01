"""Migration 001: memory.json v1 -> v2 schema.

Bumps the on-disk memory format from the legacy flat shape to the structured
v2 schema with typed sections (context, preferences, facts, goals).

This is a soft migration: the original file is preserved as memory.legacy.json.
"""

from __future__ import annotations

MIGRATION_ID = "001_memory_v2"
DESCRIPTION = "Upgrade memory.json to v2 structured schema"


def UP(cursor) -> None:
    # Migration logic operates on files, not the DB directly.
    # The runner provides a cursor for DB migrations; file migrations
    # use the Path-based approach in migrate_memory_schema.py.
    pass


def DOWN(cursor) -> None:
    pass
