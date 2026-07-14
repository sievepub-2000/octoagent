"""Migration runner for OctoAgent database schemas.

Discovers all migration modules under this package, executes them in order,
and tracks applied migrations in an ``_migrations`` table (created on first run).

Usage:
    from scripts.migrations.runner import run_migrations, rollback_migration

    # apply all pending
    run_migrations(cursor)

    # roll back last
    rollback_migration(cursor, migration_id="001_memory_v2")
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from . import __path__ as _pkg_path

MIGRATIONS_TABLE = "_applied_migrations"


def _discover_migrations() -> list[dict[str, Any]]:
    """Discover all migration modules in the package."""
    migrations = []
    for importer, modname, ispkg in pkgutil.iter_modules(_pkg_path):
        if modname.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f".{modname}", package=__package__)
            migration_id = getattr(mod, "MIGRATION_ID", None)
            if not migration_id:
                continue
            migrations.append(
                {
                    "id": migration_id,
                    "module": mod,
                    "description": getattr(mod, "DESCRIPTION", ""),
                }
            )
        except Exception as exc:
            print(f"WARNING: failed to load migration {modname}: {exc}")
    migrations.sort(key=lambda m: m["id"])
    return migrations


def run_migrations(cursor: Any, dry_run: bool = False) -> list[str]:
    """Apply all pending migrations. Returns list of applied migration IDs."""
    cursor.execute(f"CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (migration_id TEXT PRIMARY KEY, applied_at INTEGER)")
    cursor.execute(f"SELECT migration_id FROM {MIGRATIONS_TABLE}")
    applied = {row[0] for row in cursor.fetchall()}

    migrations = _discover_migrations()
    applied_ids = []
    for mig in migrations:
        if mig["id"] in applied:
            continue
        if dry_run:
            print(f"[DRY RUN] would apply: {mig['id']} - {mig['description']}")
            continue
        print(f"Applying migration: {mig['id']} - {mig['description']}")
        mig["module"].UP(cursor)
        cursor.execute(
            f"INSERT INTO {MIGRATIONS_TABLE} (migration_id, applied_at) VALUES (?, ?)",
            (mig["id"], 0),  # timestamp handled by caller if needed
        )
        applied_ids.append(mig["id"])

    if not dry_run:
        print(f"Applied {len(applied_ids)} migration(s).")
    return applied_ids


def rollback_migration(cursor: Any, migration_id: str) -> bool:
    """Roll back a single migration by ID. Returns True on success."""
    migrations = _discover_migrations()
    target = next((m for m in migrations if m["id"] == migration_id), None)
    if not target:
        print(f"Migration {migration_id} not found.")
        return False
    mod = target["module"]
    if not hasattr(mod, "DOWN"):
        print(f"Migration {migration_id} has no DOWN (rollback) function.")
        return False
    print(f"Rolling back: {migration_id} - {target['description']}")
    mod.DOWN(cursor)
    cursor.execute(
        f"DELETE FROM {MIGRATIONS_TABLE} WHERE migration_id = ?",
        (migration_id,),
    )
    print(f"Rolled back: {migration_id}")
    return True


def list_migrations() -> None:
    """Print all discovered migrations and their status."""
    migrations = _discover_migrations()
    if not migrations:
        print("No migrations found.")
        return
    for mig in migrations:
        print(f"  {mig['id']:30s} {mig['description']}")
