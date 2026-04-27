"""Document format conversion tool — convert between text formats.

Uses markitdown for Office→Markdown, markdownify for HTML→Markdown,
and built-in markdown for Markdown→HTML.  All dependencies already exist
in the project.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from src.agents.thread_state import ThreadState
from src.sandbox.tools import get_thread_data, replace_virtual_path

logger = logging.getLogger(__name__)


@tool("convert_document", parse_docstring=True)
def convert_document_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    input_path: str,
    target_format: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Convert a document file to another format.

    Supported conversions:
      - Office files (docx, xlsx, pptx, pdf) → Markdown  (via markitdown)
      - HTML files → Markdown  (via markdownify)
      - Markdown files → HTML  (via Python markdown)
      - CSV files → Markdown table
      - JSON files → formatted Markdown code block
      - Any text file → plain text extract

    Args:
        input_path: Absolute path to the source file.
        target_format: Target format — "markdown", "html", "text", "json".
    """
    thread_data = get_thread_data(runtime)
    actual_path = replace_virtual_path(input_path, thread_data)
    path = Path(actual_path)

    if not path.is_file():
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Error: File not found: {input_path}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    suffix = path.suffix.lower()
    target = target_format.lower().strip()

    # ---- Office/PDF → Markdown via markitdown ----
    office_exts = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
    if suffix in office_exts and target in ("markdown", "md"):
        try:
            from markitdown import MarkItDown

            md = MarkItDown()
            result = md.convert(str(path))
            out_path = path.with_suffix(".md")
            out_path.write_text(result.text_content, encoding="utf-8")
            preview = result.text_content[:3000]
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"Converted {path.name} → {out_path.name}\n\nPreview:\n{preview}",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        except ImportError:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "Error: markitdown not installed.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        except Exception as exc:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"Error converting {path.name}: {exc}",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

    # ---- HTML → Markdown ----
    if suffix in (".html", ".htm") and target in ("markdown", "md"):
        try:
            from markdownify import markdownify

            html = path.read_text(encoding="utf-8", errors="replace")
            md_text = markdownify(html, heading_style="ATX", strip=["script", "style"])
            out_path = path.with_suffix(".md")
            out_path.write_text(md_text, encoding="utf-8")
            preview = md_text[:3000]
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"Converted {path.name} → {out_path.name}\n\nPreview:\n{preview}",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        except ImportError:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "Error: markdownify not installed.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

    # ---- Markdown → HTML ----
    if suffix == ".md" and target == "html":
        import markdown as md_lib

        md_text = path.read_text(encoding="utf-8", errors="replace")
        html = md_lib.markdown(md_text, extensions=["tables", "fenced_code", "toc"])
        out_path = path.with_suffix(".html")
        template = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{path.stem}</title></head>
<body>{html}</body>
</html>"""
        out_path.write_text(template, encoding="utf-8")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Converted {path.name} → {out_path.name}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    # ---- CSV → Markdown table ----
    if suffix == ".csv" and target in ("markdown", "md"):
        import csv

        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            return Command(
                update={
                    "messages": [
                        ToolMessage("CSV file is empty.", tool_call_id=tool_call_id)
                    ]
                }
            )
        header = rows[0]
        lines = ["| " + " | ".join(header) + " |"]
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for row in rows[1:200]:  # cap at 200 rows
            lines.append("| " + " | ".join(row) + " |")
        if len(rows) > 201:
            lines.append(f"\n... ({len(rows) - 201} more rows)")
        md_text = "\n".join(lines)
        out_path = path.with_suffix(".md")
        out_path.write_text(md_text, encoding="utf-8")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Converted {path.name} → {out_path.name} ({len(rows)-1} rows)",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    # ---- JSON → Markdown code block ----
    if suffix == ".json" and target in ("markdown", "md"):
        import json

        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            obj = json.loads(text)
            formatted = json.dumps(obj, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            formatted = text
        md_text = f"```json\n{formatted[:30000]}\n```"
        out_path = path.with_suffix(".md")
        out_path.write_text(md_text, encoding="utf-8")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Converted {path.name} → {out_path.name}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    # ---- Fallback: any text → plain text extract ----
    if target == "text":
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            if len(content) > 60_000:
                content = content[:60_000] + "\n\n... (truncated)"
            return Command(
                update={
                    "messages": [
                        ToolMessage(content, tool_call_id=tool_call_id)
                    ]
                }
            )
        except Exception as exc:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"Error reading file: {exc}",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

    return Command(
        update={
            "messages": [
                ToolMessage(
                    f"Error: Unsupported conversion {suffix} → {target}. "
                    "Supported: Office→markdown, HTML→markdown, Markdown→html, CSV→markdown, JSON→markdown, any→text.",
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )
