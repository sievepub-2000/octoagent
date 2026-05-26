#!/usr/bin/env python3
"""Prefix-aware backend<->frontend API audit.

Walks backend/src/gateway/routers/*.py, parses APIRouter(prefix=...) and every
@router.METHOD("/path"), produces a list of full backend paths. Then walks the
frontend tree for `/api/...` references (including those in template literals,
where `${var}` is normalized to `{var}` and treated as a wildcard segment).

Outputs docs/api_drift_audit.md (v2) with three sections:
  A: backend routes with no frontend reference (TRULY dead candidates)
  B: frontend URLs with no backend route (drift / proxy / ws)
  C: matched pairs

Matching rule: each backend full path is compiled to a regex where {var} -> [^/]+
and matched against each frontend URL (anchored). A backend route is "covered"
if any frontend URL matches.
"""
from __future__ import annotations
import re, sys, json
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
ROUTERS_DIR = ROOT / "backend" / "src" / "gateway" / "routers"
FRONTEND_DIR = ROOT / "frontend" / "src"

ROUTE_DECO = re.compile(
    r'@router\.(get|post|put|delete|patch|options|head|websocket)\(\s*[\"\'](?P<path>[^\"\']+)[\"\']'
)
PREFIX_RE = re.compile(r'APIRouter\([^)]*prefix\s*=\s*[\"\'](?P<prefix>[^\"\']*)[\"\']')

def parse_router(file: Path) -> tuple[str, list[tuple[str, str]]]:
    text = file.read_text(encoding="utf-8", errors="replace")
    m = PREFIX_RE.search(text)
    prefix = m.group("prefix") if m else ""
    routes: list[tuple[str, str]] = []
    for rm in ROUTE_DECO.finditer(text):
        method = rm.group(1).upper()
        path = rm.group("path")
        routes.append((method, prefix + path))
    return prefix, routes

# Collect backend routes
backend: list[tuple[str, str, str]] = []  # (file, method, fullpath)
for f in sorted(ROUTERS_DIR.glob("*.py")):
    if f.name.startswith("__"):
        continue
    _, routes = parse_router(f)
    for method, full in routes:
        backend.append((f.name, method, full))

# Collect frontend /api/... URLs (handles backtick template literals with nested parens)
fe_urls: list[tuple[str, str]] = []

def extract_string_literal(text: str, start: int, quote: str) -> tuple[str, int] | None:
    """Starting AT the opening quote at text[start], return (content, end_idx_after_close).
    Handles ${...} inside backticks with nested braces and parens."""
    i = start + 1
    out: list[str] = []
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            out.append(text[i:i+2]); i += 2; continue
        if quote == "`" and ch == "$" and i + 1 < n and text[i+1] == "{":
            # consume ${...} with brace tracking
            j = i + 2
            depth = 1
            while j < n and depth > 0:
                cj = text[j]
                if cj == "{": depth += 1
                elif cj == "}": depth -= 1
                elif cj == "\\": j += 1
                j += 1
            out.append(text[i:j])
            i = j
            continue
        if ch == quote:
            return "".join(out), i + 1
        out.append(ch)
        i += 1
    return None

def find_api_urls(text: str) -> list[str]:
    urls: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch in ("`", "'", '"'):
            r = extract_string_literal(text, i, ch)
            if r is None:
                i += 1; continue
            content, end = r
            stripped = content.lstrip()
            if stripped.startswith("/api/") or stripped.startswith("/ws/"):
                # Normalize ${...} -> {x}
                norm = re.sub(r"\$\{[^}]*\}", "{x}", stripped)
                norm = norm.split("?", 1)[0].rstrip("/")
                if norm:
                    urls.append(norm)
            i = end
        else:
            i += 1
    return urls

for f in FRONTEND_DIR.rglob("*"):
    if f.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
        continue
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    for url in find_api_urls(text):
        rel = str(f.relative_to(ROOT))
        fe_urls.append((url, rel))

# Dedup frontend URLs but keep all source files per URL
from collections import defaultdict
fe_index: dict[str, list[str]] = defaultdict(list)
for u, src in fe_urls:
    fe_index[u].append(src)

def compile_backend(full: str) -> re.Pattern:
    pat = re.sub(r"\{[^}]+\}", r"[^/]+", full.rstrip("/"))
    return re.compile(rf"^{pat}/?$")

# Match
matched_backend: set[tuple[str, str]] = set()  # (method, fullpath)
matched_fe: set[str] = set()
for file, method, full in backend:
    pat = compile_backend(full)
    for u in fe_index:
        # frontend wildcard {x} matched by [^/]+ as well; replace before regex
        u_for_match = re.sub(r"\{[^}]+\}", "PLACEHOLDER", u)
        if pat.match(u_for_match):
            matched_backend.add((method, full))
            matched_fe.add(u)

# Second pass: treat frontend URL as matched if it is a strict path prefix
# of any backend full path (handles base-URL constants like '/api/execution-nodes').
backend_fulls = [full for _, _, full in backend]
for u in list(fe_index):
    if u in matched_fe:
        continue
    u_norm = re.sub(r"\{[^}]+\}", "PLACEHOLDER", u).rstrip("/")
    if not u_norm:
        continue
    for full in backend_fulls:
        full_norm = re.sub(r"\{[^}]+\}", "PLACEHOLDER", full)
        if full_norm == u_norm or full_norm.startswith(u_norm + "/"):
            matched_fe.add(u)
            break

# Third pass: frontend URL with {x} placeholders matches backend full path if
# its compiled regex matches the backend full path (handles cases where frontend
# templates a segment that is a literal in backend, e.g. /api/task-workspaces/{x}/{x}
# vs backend /api/task-workspaces/{task_id}/studio-runtime).
def compile_frontend(u: str) -> re.Pattern:
    pat = re.escape(u)
    # un-escape placeholder regex sources
    pat = pat.replace(r"\{x\}", "[^/]+")
    return re.compile(rf"^{pat}/?$")

for u in list(fe_index):
    if u in matched_fe:
        continue
    if "{x}" not in u:
        continue
    fe_pat = compile_frontend(u)
    for full in backend_fulls:
        full_norm = re.sub(r"\{[^}]+\}", "PLACEHOLDER", full)
        if fe_pat.match(full_norm):
            matched_fe.add(u)
            break

# Sections
unmatched_be = [b for b in backend if (b[1], b[2]) not in matched_backend]
unmatched_fe = sorted(u for u in fe_index if u not in matched_fe)
matched_pairs = [b for b in backend if (b[1], b[2]) in matched_backend]

# Group A by file
by_file: dict[str, list[tuple[str, str]]] = defaultdict(list)
for file, m, p in unmatched_be:
    by_file[file].append((m, p))

# Write report
out = ROOT / "docs" / "api_drift_audit.md"
lines: list[str] = []
lines.append("# Backend↔Frontend API drift audit (v2, prefix-aware)\n\n")
lines.append(f"- Backend routes scanned: **{len(backend)}**\n")
lines.append(f"- Frontend `/api/...` literal URLs (unique): **{len(fe_index)}**\n")
lines.append(f"- Backend routes covered by a frontend URL: **{len(matched_backend)}**\n")
lines.append(f"- Frontend URLs matched to a backend route:   **{len(matched_fe)}**\n\n")
lines.append("Matching: backend `{var}` segments treated as `[^/]+`; frontend `${expr}` likewise.\n")
lines.append("Caveat: this still misses HTTP calls assembled from non-literal base URLs (e.g. `fetch(url)` where `url` is built elsewhere), so section A must still be cross-checked.\n\n")

lines.append(f"## A. Backend routes with no frontend reference ({len(unmatched_be)})\n\n")
for file in sorted(by_file):
    routes = sorted(by_file[file])
    lines.append(f"### `{file}` ({len(routes)})\n\n")
    for m, p in routes:
        lines.append(f"- `{m:<6} {p}`\n")
    lines.append("\n")

lines.append(f"## B. Frontend URLs not matching any backend route ({len(unmatched_fe)})\n\n")
for u in unmatched_fe:
    srcs = ", ".join(sorted(set(fe_index[u]))[:3])
    lines.append(f"- `{u}` — {srcs}\n")
lines.append("\n")

lines.append(f"## C. Matched pairs ({len(matched_pairs)})\n\n")
for file, m, p in sorted(matched_pairs):
    lines.append(f"- `{m:<6} {p}` ← `{file}`\n")

out.write_text("".join(lines), encoding="utf-8")
print(f"wrote {out} : A={len(unmatched_be)} B={len(unmatched_fe)} C={len(matched_pairs)}")
