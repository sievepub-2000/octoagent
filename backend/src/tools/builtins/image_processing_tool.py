"""Image processing tool — resize, convert, compress, metadata.

Uses Pillow (PIL) for all operations.  Pillow is widely used (80M+ downloads/month)
and has no native-code dependencies beyond libjpeg / libpng which ship with most
Linux distributions.
"""

from __future__ import annotations

import json
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


def _ensure_pillow():
    """Lazy-import Pillow so the tool file parses even if PIL isn't installed."""
    try:
        from PIL import Image  # noqa: F401

        return Image
    except ImportError:
        return None


@tool("process_image", parse_docstring=True)
def process_image_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    image_path: str,
    operation: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    width: int | None = None,
    height: int | None = None,
    output_format: str | None = None,
    quality: int = 85,
) -> Command:
    """Process an image file — resize, convert format, compress, or extract metadata.

    Supported operations:
      - "info"     — return image metadata (size, format, mode, EXIF).
      - "resize"   — resize to given width/height (preserves aspect if one is 0).
      - "convert"  — convert to output_format (png, jpeg, webp).
      - "compress" — re-encode at given quality (1-100).
      - "thumbnail" — create a max 256 px thumbnail.

    Args:
        image_path: Absolute path to the source image.
        operation: One of "info", "resize", "convert", "compress", "thumbnail".
        width: Target width for resize (optional, 0 to auto-calc from height).
        height: Target height for resize (optional, 0 to auto-calc from width).
        output_format: Target format for convert (e.g. "png", "jpeg", "webp").
        quality: JPEG/WebP quality 1-100 (default 85).
    """
    Image = _ensure_pillow()
    if Image is None:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "Error: Pillow is not installed. Run: pip install Pillow",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    thread_data = get_thread_data(runtime)
    actual_path = replace_virtual_path(image_path, thread_data)
    path = Path(actual_path)

    if not path.is_file():
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Error: Image file not found: {image_path}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    try:
        img = Image.open(path)
    except Exception as exc:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Error opening image: {exc}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    operation = operation.lower().strip()

    # ---- info ----
    if operation == "info":
        info: dict = {
            "width": img.width,
            "height": img.height,
            "format": img.format,
            "mode": img.mode,
            "file_size_bytes": path.stat().st_size,
        }
        exif = img.getexif()
        if exif:
            info["exif_tag_count"] = len(exif)
        return Command(
            update={
                "messages": [
                    ToolMessage(json.dumps(info, indent=2), tool_call_id=tool_call_id)
                ]
            }
        )

    # ---- resize ----
    if operation == "resize":
        w = width or 0
        h = height or 0
        if w == 0 and h == 0:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "Error: Provide at least width or height for resize.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        if w == 0:
            w = int(img.width * (h / img.height))
        if h == 0:
            h = int(img.height * (w / img.width))
        img = img.resize((w, h), Image.LANCZOS)
        out_path = path.with_stem(f"{path.stem}_resized")
        img.save(out_path, quality=quality)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Resized to {w}x{h} → {out_path}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    # ---- convert ----
    if operation == "convert":
        fmt = (output_format or "png").lower()
        allowed = {"png", "jpeg", "jpg", "webp", "bmp", "tiff"}
        if fmt not in allowed:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"Error: Unsupported format '{fmt}'. Use: {', '.join(sorted(allowed))}",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        if fmt == "jpg":
            fmt = "jpeg"
        if img.mode == "RGBA" and fmt == "jpeg":
            img = img.convert("RGB")
        out_path = path.with_suffix(f".{fmt}")
        img.save(out_path, format=fmt.upper(), quality=quality)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Converted to {fmt} → {out_path}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    # ---- compress ----
    if operation == "compress":
        q = max(1, min(100, quality))
        fmt = img.format or "JPEG"
        if img.mode == "RGBA" and fmt.upper() == "JPEG":
            img = img.convert("RGB")
        out_path = path.with_stem(f"{path.stem}_compressed")
        img.save(out_path, format=fmt, quality=q, optimize=True)
        old_size = path.stat().st_size
        new_size = out_path.stat().st_size
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Compressed {old_size} → {new_size} bytes (quality={q}) → {out_path}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    # ---- thumbnail ----
    if operation == "thumbnail":
        img.thumbnail((256, 256), Image.LANCZOS)
        out_path = path.with_stem(f"{path.stem}_thumb")
        img.save(out_path, quality=quality)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Thumbnail {img.width}x{img.height} → {out_path}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    return Command(
        update={
            "messages": [
                ToolMessage(
                    f"Error: Unknown operation '{operation}'. Use: info, resize, convert, compress, thumbnail.",
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )
