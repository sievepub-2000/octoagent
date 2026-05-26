#!/usr/bin/env python3
"""Reseal the integrity fingerprint in ``backend/src/governance/about.py``.

Run this script after legitimately editing ``_CONTACT_EMAIL`` or
``_ABOUT_BODY`` in :mod:`src.governance.about`. It rewrites the
``_INTEGRITY_FINGERPRINT`` constant in-place with the freshly computed
SHA-256 digest.

USAGE:
    python scripts/dev_tools/refresh_about_fingerprint.py

This script never reads or writes the internal master key. It only
rewrites a single hex string in the source file.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[2]


def main() -> int:
    target = _repo_root() / "backend" / "src" / "governance" / "about.py"
    if not target.is_file():
        print(f"ERROR: cannot find {target}", file=sys.stderr)
        return 2
    src = target.read_text(encoding="utf-8")

    email_match = re.search(r'_CONTACT_EMAIL\s*=\s*"([^"\n]+)"', src)
    body_match = re.search(r'_ABOUT_BODY\s*=\s*"""(.*?)"""', src, re.DOTALL)
    if not email_match or not body_match:
        print("ERROR: could not locate _CONTACT_EMAIL or _ABOUT_BODY", file=sys.stderr)
        return 3
    email = email_match.group(1)
    body = body_match.group(1)
    payload = email.encode("utf-8") + b"|" + body.encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()

    new_src, n = re.subn(
        r'_INTEGRITY_FINGERPRINT\s*=\s*"[^\n]*"',
        f'_INTEGRITY_FINGERPRINT = "{digest}"',
        src,
        count=1,
    )
    if n != 1:
        print("ERROR: could not rewrite _INTEGRITY_FINGERPRINT", file=sys.stderr)
        return 4
    target.write_text(new_src, encoding="utf-8")
    print(f"Resealed {target}")
    print(f"  contact_email = {email}")
    print(f"  body_chars    = {len(body)}")
    print(f"  fingerprint   = {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
