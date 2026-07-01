"""Versioned database migration modules.

Each module exposes:
  - MIGRATION_ID: str
  - DESCRIPTION: str
  - UP(cursor): callable
  - DOWN(cursor): callable (optional rollback)
"""
