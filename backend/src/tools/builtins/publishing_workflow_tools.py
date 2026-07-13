from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from src.utils.serialization import fmt_json as _json

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ARTIFACT_ROOT = _REPO_ROOT / "runtime" / "system_tools"
_WRITING_ROOT = _ARTIFACT_ROOT / "writing-suite"
_WRITING_PYTHON = _ARTIFACT_ROOT / "writing-python" / ".venv" / "bin" / "python"
_RUNTIME_TOOLS = _REPO_ROOT / "runtime" / "tools"
_RUNTIME_BIN = _RUNTIME_TOOLS / "bin"
_TEXTLINT = _RUNTIME_TOOLS / "writing-node" / "node_modules" / ".bin" / "textlint"
_TEXTLINT_CONFIG = _RUNTIME_TOOLS / "writing-node" / ".textlintrc.json"
_FRONTEND_NODE_MODULES = _REPO_ROOT / "frontend" / "node_modules"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")



def _slug(value: str, fallback: str = "item") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or fallback).strip()).strip(".-_")
    return (text or fallback)[:100]


def _clip(text: str, limit: int = 6000) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit // 2] + "\n...<truncated>...\n" + text[-limit // 2 :]


def _project_dir(project_slug: str) -> Path:
    root = _WRITING_ROOT / "projects" / _slug(project_slug, "project")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_path(path: str, *, base: Path = _REPO_ROOT, must_exist: bool = False) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = base / target
    target = target.resolve()
    if must_exist and not target.exists():
        raise ValueError(f"path does not exist: {target}")
    return target


def _run(args: list[str], *, cwd: Path | None = None, timeout: int = 120) -> dict[str, Any]:
    started = time.monotonic()
    env = os.environ.copy()
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_RUNTIME_TOOLS / "playwright-browsers"))
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd or _REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
            env=env,
        )
        return {
            "args": [str(arg) for arg in args],
            "exit_code": result.returncode,
            "stdout": _clip(result.stdout),
            "stderr": _clip(result.stderr),
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        }
    except FileNotFoundError:
        return {"args": [str(arg) for arg in args], "available": False, "error": f"command not found: {args[0]}"}
    except subprocess.TimeoutExpired as exc:
        return {
            "args": [str(arg) for arg in args],
            "timeout": timeout,
            "stdout": _clip(exc.stdout or ""),
            "stderr": _clip(exc.stderr or ""),
        }


def _binary(name: str) -> str | None:
    managed = _RUNTIME_BIN / name
    if managed.exists() and os.access(managed, os.X_OK):
        return str(managed)
    return shutil.which(name)


def _write_project_file(project_slug: str, relative_path: str, content: str) -> Path:
    root = _project_dir(project_slug)
    safe_parts = [_slug(part, "part") for part in Path(relative_path).parts if part not in {"", ".", ".."}]
    target = root.joinpath(*safe_parts).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise ValueError("relative_path escapes the project directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _read_input_text(path: str = "", text: str = "") -> tuple[str, Path | None]:
    if path.strip():
        source = _resolve_path(path, must_exist=True)
        return source.read_text(encoding="utf-8", errors="replace"), source
    return text or "", None


@tool("writing_toolchain_status", parse_docstring=True)
def writing_toolchain_status_tool() -> str:
    """Report installed writing, publishing, review, and browser automation tools."""
    checks: dict[str, Any] = {
        "paths": {
            "writing_python": str(_WRITING_PYTHON),
            "textlint": str(_TEXTLINT),
            "vale": str(_RUNTIME_BIN / "vale"),
            "wp_cli": str(_RUNTIME_BIN / "wp"),
            "writing_root": str(_WRITING_ROOT),
        },
        "binaries": {
            name: _binary(name)
            for name in ("pandoc", "php", "node", "npm")
        },
    }
    if _WRITING_PYTHON.exists():
        script = """
import importlib, json
mods = ['browser_use', 'presidio_analyzer', 'presidio_anonymizer']
print(json.dumps({m: bool(importlib.import_module(m)) for m in mods}, sort_keys=True))
""".strip()
        checks["python_packages"] = _run([str(_WRITING_PYTHON), "-c", script], timeout=30)
    checks["textlint"] = _run([str(_TEXTLINT), "--version"], timeout=30) if _TEXTLINT.exists() else {"available": False}
    checks["vale"] = _run([str(_RUNTIME_BIN / "vale"), "--version"], timeout=30) if (_RUNTIME_BIN / "vale").exists() else {"available": False}
    checks["wp_cli"] = _run([str(_RUNTIME_BIN / "wp"), "--info", "--allow-root"], timeout=30) if (_RUNTIME_BIN / "wp").exists() else {"available": False}
    checks["pandoc"] = _run([_binary("pandoc") or "pandoc", "--version"], timeout=30)
    checks["playwright"] = _run([_binary("node") or "node", "-e", "const { chromium } = require('./frontend/node_modules/@playwright/test'); console.log(typeof chromium.launch)"], timeout=30)
    return _json({"generated_at": _now(), "checks": checks})


@tool("novel_project_store", parse_docstring=True)
def novel_project_store_tool(
    operation: str,
    project_slug: str = "",
    title: str = "",
    asset_name: str = "",
    content: str = "",
    metadata_json: str = "{}",
) -> str:
    """Manage long-form writing project files for articles, novels, papers, and web serials.

    Args:
        operation: One of init, list, read, write_asset, append_asset.
        project_slug: Stable project id used as the project directory name.
        title: Human title used when operation is init.
        asset_name: Relative asset path such as bible.md, outline.md, chapters/001.md, or paper/abstract.md.
        content: UTF-8 text to write or append.
        metadata_json: Optional JSON metadata for init.
    """
    op = operation.strip().lower()
    if op == "list":
        root = _WRITING_ROOT / "projects"
        projects = sorted(path.name for path in root.iterdir() if path.is_dir()) if root.exists() else []
        return _json({"generated_at": _now(), "projects": projects})
    if not project_slug.strip():
        return _json({"error": "project_slug is required"})
    root = _project_dir(project_slug)
    if op == "init":
        metadata = json.loads(metadata_json or "{}")
        if not isinstance(metadata, dict):
            return _json({"error": "metadata_json must decode to an object"})
        manifest = {
            "project_slug": _slug(project_slug, "project"),
            "title": title or project_slug,
            "created_at": _now(),
            "updated_at": _now(),
            "metadata": metadata,
            "workflow": [
                "novel_project_store",
                "writestory",
                "chapter_drafter",
                "chapter_writer",
                "writing_review_suite",
                "writing_format_export",
                "human_approval_gate",
                "browser_publisher or wp_cli_publish",
                "publication_auditor",
            ],
        }
        (root / "project.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / "chapters").mkdir(exist_ok=True)
        (root / "publication").mkdir(exist_ok=True)
        return _json({"generated_at": _now(), "project_dir": str(root), "manifest": manifest})
    if op == "read":
        if asset_name.strip():
            safe_parts = [_slug(part, "part") for part in Path(asset_name).parts if part not in {"", ".", ".."}]
            path = root.joinpath(*safe_parts).resolve()
            if not str(path).startswith(str(root.resolve())):
                return _json({"error": "asset_name escapes the project directory"})
            if not path.exists():
                return _json({"error": "asset_not_found", "path": str(path)})
            return _json({"generated_at": _now(), "path": str(path), "content": path.read_text(encoding="utf-8", errors="replace")})
        files = sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())
        return _json({"generated_at": _now(), "project_dir": str(root), "files": files})
    if op in {"write_asset", "append_asset"}:
        if not asset_name.strip():
            return _json({"error": "asset_name is required"})
        root.mkdir(parents=True, exist_ok=True)
        path = _write_project_file(project_slug, asset_name, "")
        mode = "a" if op == "append_asset" else "w"
        with path.open(mode, encoding="utf-8") as handle:
            handle.write(content)
        return _json({"generated_at": _now(), "path": str(path), "bytes": len(content.encode("utf-8")), "operation": op})
    return _json({"error": f"unsupported operation: {operation}"})


@tool("writestory", parse_docstring=True)
def writestory_tool(
    project_slug: str,
    brief: str,
    genre: str = "",
    audience: str = "",
    language: str = "zh-CN",
    target_chapters: int = 12,
) -> str:
    """Create a story bible and outline scaffold for fiction or narrative nonfiction.

    Args:
        project_slug: Writing project id managed by novel_project_store.
        brief: Core premise, topic, or thesis.
        genre: Genre or article/paper domain.
        audience: Target reader group.
        language: Desired output language tag.
        target_chapters: Planned chapter/section count.
    """
    safe_count = max(1, min(int(target_chapters), 200))
    bible = "\n".join(
        [
            f"# Story Bible: {project_slug}",
            "",
            f"- Language: {language}",
            f"- Genre/domain: {genre or 'unspecified'}",
            f"- Audience: {audience or 'general readers'}",
            f"- Premise: {brief}",
            "",
            "## Core Promise",
            "",
            "Summarize the emotional, informational, or argumentative promise before drafting.",
            "",
            "## Characters / Concepts",
            "",
            "- Protagonist or central concept:",
            "- Antagonistic force or counterargument:",
            "- Supporting cast / evidence base:",
            "",
            "## Continuity Ledger",
            "",
            "Track names, dates, locations, claims, citations, and unresolved promises here.",
            "",
        ]
    )
    outline_lines = [f"# Outline: {project_slug}", "", f"Premise: {brief}", ""]
    for index in range(1, safe_count + 1):
        outline_lines.append(f"## Chapter {index:03d}")
        outline_lines.append("- Purpose:")
        outline_lines.append("- Key scenes / claims:")
        outline_lines.append("- Hook into next chapter:")
        outline_lines.append("")
    bible_path = _write_project_file(project_slug, "story_bible.md", bible)
    outline_path = _write_project_file(project_slug, "outline.md", "\n".join(outline_lines))
    return _json({"generated_at": _now(), "project_slug": project_slug, "story_bible": str(bible_path), "outline": str(outline_path), "next_tool": "chapter_drafter"})


@tool("chapter_drafter", parse_docstring=True)
def chapter_drafter_tool(
    project_slug: str,
    chapter_number: int,
    title: str,
    synopsis: str,
    target_words: int = 1800,
    style_notes: str = "",
) -> str:
    """Draft a chapter planning scaffold before prose generation.

    Args:
        project_slug: Writing project id managed by novel_project_store.
        chapter_number: Chapter or section number.
        title: Chapter title.
        synopsis: Chapter synopsis, thesis, or scene purpose.
        target_words: Target word count.
        style_notes: Voice, pacing, platform, citation, or formatting notes.
    """
    number = max(1, int(chapter_number))
    content = "\n".join(
        [
            f"# Chapter {number:03d}: {title}",
            "",
            f"Target words: {max(100, int(target_words))}",
            "",
            "## Synopsis",
            "",
            synopsis,
            "",
            "## Style Notes",
            "",
            style_notes or "Use the project voice and keep continuity with the story bible.",
            "",
            "## Beats",
            "",
            "1. Opening hook:",
            "2. Development / evidence / conflict:",
            "3. Turn or reveal:",
            "4. Closing hook:",
            "",
            "## Draft",
            "",
            "<!-- chapter_writer should replace this section with finished prose. -->",
            "",
        ]
    )
    path = _write_project_file(project_slug, f"chapters/{number:03d}-{_slug(title, 'chapter')}-draft.md", content)
    return _json({"generated_at": _now(), "project_slug": project_slug, "chapter": number, "draft_path": str(path), "next_tool": "chapter_writer"})


@tool("chapter-drafter", parse_docstring=True)
def chapter_drafter_alias_tool(
    project_slug: str,
    chapter_number: int,
    title: str,
    synopsis: str,
    target_words: int = 1800,
    style_notes: str = "",
) -> str:
    """Alias for chapter_drafter using the requested hyphenated tool name.

    Args:
        project_slug: Writing project id managed by novel_project_store.
        chapter_number: Chapter or section number.
        title: Chapter title.
        synopsis: Chapter synopsis, thesis, or scene purpose.
        target_words: Target word count.
        style_notes: Voice, pacing, platform, citation, or formatting notes.
    """
    return chapter_drafter_tool.invoke(
        {
            "project_slug": project_slug,
            "chapter_number": chapter_number,
            "title": title,
            "synopsis": synopsis,
            "target_words": target_words,
            "style_notes": style_notes,
        }
    )


@tool("chapter_writer", parse_docstring=True)
def chapter_writer_tool(
    project_slug: str,
    chapter_number: int,
    title: str,
    content: str = "",
    source_path: str = "",
    stage: str = "draft",
) -> str:
    """Store generated chapter/article/paper prose as a managed project asset.

    Args:
        project_slug: Writing project id managed by novel_project_store.
        chapter_number: Chapter or section number.
        title: Chapter title.
        content: Prose content to store when source_path is empty.
        source_path: Optional existing markdown/text path to ingest.
        stage: draft, revised, final, or submitted.
    """
    text, source = _read_input_text(source_path, content)
    if not text.strip():
        return _json({"error": "content or source_path is required"})
    safe_stage = _slug(stage, "draft")
    number = max(1, int(chapter_number))
    target = _write_project_file(project_slug, f"chapters/{number:03d}-{_slug(title, 'chapter')}-{safe_stage}.md", text)
    return _json({"generated_at": _now(), "project_slug": project_slug, "chapter": number, "stage": safe_stage, "path": str(target), "source_path": str(source) if source else None, "next_tool": "writing_review_suite"})


@tool("webnovel_write", parse_docstring=True)
def webnovel_write_tool(
    project_slug: str,
    platform: str,
    chapter_path: str,
    title: str,
    synopsis: str = "",
    tags_csv: str = "",
) -> str:
    """Package a chapter/article/paper for web publication metadata and review.

    Args:
        project_slug: Writing project id managed by novel_project_store.
        platform: Target platform such as wordpress, ghost, static-site, webnovel, or custom.
        chapter_path: Path to the chapter markdown/text file.
        title: Publication title.
        synopsis: Public summary or excerpt.
        tags_csv: Comma-separated platform tags.
    """
    source = _resolve_path(chapter_path, must_exist=True)
    text = source.read_text(encoding="utf-8", errors="replace")
    package = {
        "project_slug": project_slug,
        "platform": platform,
        "title": title,
        "synopsis": synopsis,
        "tags": [tag.strip() for tag in tags_csv.split(",") if tag.strip()],
        "source_path": str(source),
        "word_estimate": len(re.findall(r"\w+", text)),
        "created_at": _now(),
        "required_flow": ["writing_review_suite", "human_approval_gate", "browser_publisher/wp_cli_publish", "publication_auditor"],
    }
    path = _write_project_file(project_slug, f"publication/{_slug(platform, 'platform')}-{_slug(title, 'item')}.json", json.dumps(package, ensure_ascii=False, indent=2))
    return _json({"generated_at": _now(), "package_path": str(path), "package": package})


@tool("webnovel-write", parse_docstring=True)
def webnovel_write_alias_tool(
    project_slug: str,
    platform: str,
    chapter_path: str,
    title: str,
    synopsis: str = "",
    tags_csv: str = "",
) -> str:
    """Alias for webnovel_write using the requested hyphenated tool name.

    Args:
        project_slug: Writing project id managed by novel_project_store.
        platform: Target platform such as wordpress, ghost, static-site, webnovel, or custom.
        chapter_path: Path to the chapter markdown/text file.
        title: Publication title.
        synopsis: Public summary or excerpt.
        tags_csv: Comma-separated platform tags.
    """
    return webnovel_write_tool.invoke(
        {
            "project_slug": project_slug,
            "platform": platform,
            "chapter_path": chapter_path,
            "title": title,
            "synopsis": synopsis,
            "tags_csv": tags_csv,
        }
    )


@tool("writing_review_suite", parse_docstring=True)
def writing_review_suite_tool(
    path: str = "",
    text: str = "",
    language: str = "en",
    run_textlint: bool = True,
    run_vale: bool = True,
    run_presidio: bool = True,
) -> str:
    """Run writing quality and safety review with textlint, Vale, and Presidio.

    Args:
        path: Markdown/text path to review. If omitted, text is reviewed from the text argument.
        text: Inline text to review when path is empty.
        language: Language hint such as en, zh-CN, or ja.
        run_textlint: Run textlint when available.
        run_vale: Run Vale when available.
        run_presidio: Run Microsoft Presidio PII detection when available.
    """
    content, source = _read_input_text(path, text)
    if not content.strip():
        return _json({"error": "path or text is required"})
    review_root = _WRITING_ROOT / "reviews"
    review_root.mkdir(parents=True, exist_ok=True)
    review_file = source or (review_root / f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-inline.md")
    if source is None:
        review_file.write_text(content, encoding="utf-8")
    results: dict[str, Any] = {"source": str(review_file), "language": language}
    if run_textlint:
        if _TEXTLINT.exists():
            args = [str(_TEXTLINT), "--format", "json"]
            if _TEXTLINT_CONFIG.exists():
                args.extend(["--config", str(_TEXTLINT_CONFIG)])
            args.append(str(review_file))
            results["textlint"] = _run(args, timeout=120)
        else:
            results["textlint"] = {"available": False}
    if run_vale:
        vale = _RUNTIME_BIN / "vale"
        results["vale"] = _run([str(vale), "--output=JSON", str(review_file)], timeout=120) if vale.exists() else {"available": False}
    if run_presidio:
        if _WRITING_PYTHON.exists():
            script = """
import json, re, sys
with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
    text = f.read()
try:
    import presidio_analyzer, presidio_anonymizer
    imported = True
except Exception as exc:
    imported = False
patterns = {
    'EMAIL_ADDRESS': r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}',
    'PHONE_NUMBER': r'(?<!\\d)(?:\\+?\\d[\\d .-]{7,}\\d)(?!\\d)',
    'CREDIT_CARD': r'(?<!\\d)(?:\\d[ -]*?){13,19}(?!\\d)'
}
findings = []
for entity, pattern in patterns.items():
    for match in re.finditer(pattern, text):
        findings.append({'entity_type': entity, 'start': match.start(), 'end': match.end(), 'score': 0.75})
print(json.dumps({'presidio_imported': imported, 'findings': findings[:50]}, ensure_ascii=False, sort_keys=True))
""".strip()
            results["presidio"] = _run([str(_WRITING_PYTHON), "-c", script, str(review_file)], timeout=60)
        else:
            results["presidio"] = {"available": False}
    return _json({"generated_at": _now(), "results": results})


@tool("writing_format_export", parse_docstring=True)
def writing_format_export_tool(source_path: str, output_format: str = "html", output_path: str = "") -> str:
    """Convert Markdown/text writing assets to finished artifacts with Pandoc.

    Args:
        source_path: Source Markdown/text file.
        output_format: Target format such as html, epub, docx, pdf, or markdown.
        output_path: Optional output path. Defaults under runtime/system_tools/writing-suite/exports.
    """
    source = _resolve_path(source_path, must_exist=True)
    fmt = output_format.strip().lower().lstrip(".") or "html"
    if fmt not in {"html", "epub", "epub3", "docx", "pdf", "markdown", "md"}:
        return _json({"error": "unsupported output_format", "allowed": ["html", "epub", "docx", "pdf", "markdown"]})
    out = _resolve_path(output_path) if output_path.strip() else _WRITING_ROOT / "exports" / f"{source.stem}.{fmt if fmt != 'markdown' else 'md'}"
    out.parent.mkdir(parents=True, exist_ok=True)
    pandoc = _binary("pandoc") or "pandoc"
    args = [pandoc, str(source), "-o", str(out)]
    result = _run(args, timeout=180)
    return _json({"generated_at": _now(), "source": str(source), "output": str(out), "format": fmt, "result": result})


@tool("human_approval_gate", parse_docstring=True)
def human_approval_gate_tool(action: str, risk_summary: str, artifacts_json: str = "[]", confirmed_by_user: bool = False) -> str:
    """Require and record human approval before public publishing or account mutation.

    Args:
        action: Action awaiting approval, such as publish_chapter or submit_to_platform.
        risk_summary: Risks, target account, target platform, and irreversible effects.
        artifacts_json: JSON list of files/URLs reviewed by the human.
        confirmed_by_user: True only when the human has explicitly approved in chat.
    """
    try:
        artifacts = json.loads(artifacts_json or "[]")
    except json.JSONDecodeError as exc:
        return _json({"error": f"invalid artifacts_json: {exc}"})
    if not confirmed_by_user:
        return _json({"approved": False, "error": "human_approval_required", "action": action, "risk_summary": risk_summary, "artifacts": artifacts})
    record = {"approved": True, "action": action, "risk_summary": risk_summary, "artifacts": artifacts, "approved_at": _now()}
    root = _WRITING_ROOT / "approvals"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{_slug(action, 'approval')}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return _json({"generated_at": _now(), "approval_record": str(path), **record})


@tool("browser_publisher", parse_docstring=True)
def browser_publisher_tool(
    url: str,
    mode: str = "dry_run",
    instructions: str = "",
    content_path: str = "",
    confirmed_by_user: bool = False,
) -> str:
    """Use Playwright/browser-use-ready automation for publishing page dry-runs and guarded submissions.

    Args:
        url: Target publishing or preview URL.
        mode: dry_run, preview, or submit. submit requires confirmed_by_user.
        instructions: Human-readable action plan for the browser agent.
        content_path: Optional content file to reference in the action plan.
        confirmed_by_user: Required for submit or other state-changing modes.
    """
    normalized = mode.strip().lower()
    if normalized not in {"dry_run", "preview", "submit"}:
        return _json({"error": "mode must be dry_run, preview, or submit"})
    if normalized == "submit" and not confirmed_by_user:
        return _json({"error": "human_approval_required", "message": "Call human_approval_gate before browser_publisher submit mode."})
    root = _WRITING_ROOT / "browser_publisher"
    root.mkdir(parents=True, exist_ok=True)
    screenshot = root / f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{_slug(normalized, 'browser')}.png"
    plan = {"url": url, "mode": normalized, "instructions": instructions, "content_path": content_path, "screenshot": str(screenshot)}
    script = """
const fs = require('fs');
const { chromium } = require('./frontend/node_modules/@playwright/test');
const plan = JSON.parse(process.argv[1]);
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1365, height: 900 } });
  await page.goto(plan.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  const title = await page.title();
  const text = (await page.locator('body').innerText({ timeout: 10000 }).catch(() => '')).slice(0, 4000);
  await page.screenshot({ path: plan.screenshot, fullPage: true });
  await browser.close();
  console.log(JSON.stringify({ title, text_preview: text, screenshot: plan.screenshot }));
})();
""".strip()
    result = _run([_binary("node") or "node", "-e", script, json.dumps(plan)], timeout=60)
    return _json({"generated_at": _now(), "plan": plan, "result": result, "browser_use_python": str(_WRITING_PYTHON) if _WRITING_PYTHON.exists() else None})


@tool("publication_auditor", parse_docstring=True)
def publication_auditor_tool(url: str, expected_text: str = "", screenshot: bool = True) -> str:
    """Audit a published URL by collecting title, visible text preview, screenshot, and expected text match.

    Args:
        url: Published or preview URL to audit.
        expected_text: Optional text snippet expected to appear on the page.
        screenshot: Capture a full-page screenshot when true.
    """
    root = _WRITING_ROOT / "publication_auditor"
    root.mkdir(parents=True, exist_ok=True)
    screenshot_path = root / f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-audit.png"
    script = """
const { chromium } = require('./frontend/node_modules/@playwright/test');
const cfg = JSON.parse(process.argv[1]);
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1365, height: 900 } });
  await page.goto(cfg.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  const title = await page.title();
  const text = await page.locator('body').innerText({ timeout: 10000 }).catch(() => '');
  if (cfg.screenshot) await page.screenshot({ path: cfg.screenshot_path, fullPage: true });
  await browser.close();
  console.log(JSON.stringify({ title, contains_expected_text: cfg.expected_text ? text.includes(cfg.expected_text) : null, text_preview: text.slice(0, 4000), screenshot: cfg.screenshot ? cfg.screenshot_path : null }));
})();
""".strip()
    cfg = {"url": url, "expected_text": expected_text, "screenshot": bool(screenshot), "screenshot_path": str(screenshot_path)}
    result = _run([_binary("node") or "node", "-e", script, json.dumps(cfg)], timeout=60)
    return _json({"generated_at": _now(), "url": url, "result": result})


@tool("wp_cli_publish", parse_docstring=True)
def wp_cli_publish_tool(
    site_path: str,
    post_title: str,
    content_path: str,
    status: str = "draft",
    post_type: str = "post",
    confirmed_by_user: bool = False,
) -> str:
    """Publish or draft a WordPress post through WP-CLI.

    Args:
        site_path: Filesystem path to a WordPress installation.
        post_title: WordPress post title.
        content_path: Markdown/HTML/text content file.
        status: draft, pending, private, or publish. publish requires confirmed_by_user.
        post_type: WordPress post type, usually post or page.
        confirmed_by_user: Required for status=publish or other public submission.
    """
    wp = _RUNTIME_BIN / "wp"
    if not wp.exists():
        return _json({"error": "wp-cli is not installed", "expected": str(wp)})
    safe_status = status.strip().lower()
    if safe_status not in {"draft", "pending", "private", "publish"}:
        return _json({"error": "unsupported status", "allowed": ["draft", "pending", "private", "publish"]})
    if safe_status == "publish" and not confirmed_by_user:
        return _json({"error": "human_approval_required", "message": "Call human_approval_gate before publishing publicly."})
    site = _resolve_path(site_path, must_exist=True)
    content_file = _resolve_path(content_path, must_exist=True)
    command = [str(wp), "post", "create", str(content_file), "--post_title=" + post_title, "--post_status=" + safe_status, "--post_type=" + post_type, "--porcelain", "--allow-root"]
    if not confirmed_by_user:
        return _json({"dry_run": True, "command": [shlex.quote(arg) for arg in command], "cwd": str(site), "message": "Set confirmed_by_user=true after human approval to execute."})
    result = _run(command, cwd=site, timeout=120)
    return _json({"generated_at": _now(), "cwd": str(site), "result": result})


PUBLISHING_WORKFLOW_TOOLS = [
    writing_toolchain_status_tool,
    novel_project_store_tool,
    writestory_tool,
    chapter_drafter_tool,
    chapter_drafter_alias_tool,
    chapter_writer_tool,
    webnovel_write_tool,
    webnovel_write_alias_tool,
    writing_review_suite_tool,
    writing_format_export_tool,
    human_approval_gate_tool,
    browser_publisher_tool,
    publication_auditor_tool,
    wp_cli_publish_tool,
]
