"""One-shot migration from legacy flat memory.json to the structured v2 shape.

Non-breaking: the original ``memory.json`` is preserved (copied to
``memory.legacy.json`` on first run) and a new ``memory.v2.json`` is written
alongside it. The runtime normalizer in
``backend/src/gateway/routers/memory.py`` already bridges both shapes, so this
script is purely an upgrade aid for operators who want the on-disk file to
match the WebUI schema.

Usage:
    # default workspace
    .venv/bin/python backend/scripts/migrate_memory_schema.py

    # custom path
    .venv/bin/python backend/scripts/migrate_memory_schema.py --memory /path/to/memory.json

    # dry-run (print target payload only, no writes)
    .venv/bin/python backend/scripts/migrate_memory_schema.py --dry-run
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import sys
from pathlib import Path

DEFAULT_MEMORY_PATH = Path("workspace/default/memory.json")


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_legacy(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"memory file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"memory file must contain a JSON object, got {type(data).__name__}")
    return data


def build_v2_snapshot(raw: dict) -> dict:
    """Return a v2-shaped snapshot. Mirrors ``_normalize_memory_snapshot``."""

    now = _utc_now_iso()
    user_ctx = raw.get("user_context")
    summary = user_ctx if isinstance(user_ctx, str) else ""

    user = {
        "workContext": {"summary": "", "updatedAt": now},
        "personalContext": {"summary": "", "updatedAt": now},
        "topOfMind": {"summary": summary, "updatedAt": now},
    }

    # flatten legacy history list → recentMonths summary
    history_raw = raw.get("history")
    history_summary = ""
    if isinstance(history_raw, list) and history_raw:
        parts: list[str] = []
        for item in history_raw:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("summary") or item.get("content")
                if text:
                    parts.append(str(text))
        history_summary = "\n".join(parts).strip()
    elif isinstance(history_raw, dict):
        # already structured; take recentMonths if present
        recent = history_raw.get("recentMonths") or {}
        history_summary = str(recent.get("summary") or "")

    history = {
        "recentMonths": {"summary": history_summary, "updatedAt": now},
        "earlierContext": {"summary": "", "updatedAt": now},
        "longTermBackground": {"summary": "", "updatedAt": now},
    }

    # facts: keep minimally valid entries, stamp ids if missing
    facts_clean: list[dict] = []
    facts_raw = raw.get("facts") or []
    if isinstance(facts_raw, list):
        for idx, item in enumerate(facts_raw):
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            facts_clean.append(
                {
                    "id": str(item.get("id") or f"fact_{idx}"),
                    "content": content,
                    "category": str(item.get("category") or "context"),
                    "confidence": float(item.get("confidence") or 0.5),
                    "createdAt": str(item.get("createdAt") or now),
                    "source": str(item.get("source") or "legacy"),
                }
            )

    return {
        "version": "2.0",
        "lastUpdated": now,
        "user": user,
        "history": history,
        "facts": facts_clean,
    }


def migrate(memory_path: Path, *, dry_run: bool = False) -> int:
    raw = _load_legacy(memory_path)

    if str(raw.get("version")).startswith("2"):
        print(f"[migrate-memory] {memory_path} already at v{raw.get('version')}; nothing to do.")
        return 0

    snapshot = build_v2_snapshot(raw)

    if dry_run:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return 0

    legacy_backup = memory_path.with_suffix(".legacy.json")
    v2_target = memory_path.with_name(memory_path.stem + ".v2.json")

    if not legacy_backup.exists():
        shutil.copy2(memory_path, legacy_backup)
        print(f"[migrate-memory] backed up legacy file → {legacy_backup}")
    else:
        print(f"[migrate-memory] legacy backup already present: {legacy_backup}")

    with v2_target.open("w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"[migrate-memory] wrote v2 snapshot → {v2_target}")
    print("[migrate-memory] original memory.json left untouched. The runtime "
          "normalizer bridges both shapes; flip to v2 by copying memory.v2.json "
          "over memory.json once you are comfortable.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy memory.json to v2 shape.")
    parser.add_argument(
        "--memory",
        default=str(DEFAULT_MEMORY_PATH),
        help=f"Path to memory.json (default: {DEFAULT_MEMORY_PATH}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the v2 snapshot to stdout and exit without writing.",
    )
    args = parser.parse_args(argv)
    return migrate(Path(args.memory).resolve(), dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
