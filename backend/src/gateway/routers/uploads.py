"""Upload router for handling file uploads."""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.config.paths import VIRTUAL_PATH_PREFIX, get_paths
from src.sandbox.sandbox_provider import get_sandbox_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/threads/{thread_id}/uploads", tags=["uploads"])

# Maximum upload file size: 100 MB
MAX_UPLOAD_SIZE = 100 * 1024 * 1024

# Maximum number of files per upload request
MAX_FILES_PER_UPLOAD = 20

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".toml",
    ".pdf", ".ppt", ".pptx", ".xls", ".xlsx", ".doc", ".docx",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
    ".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".go", ".rs",
    ".log", ".ini", ".cfg", ".conf", ".env",
    ".zip", ".tar", ".gz",
}

# File extensions that should be converted to markdown
CONVERTIBLE_EXTENSIONS = {
    ".pdf",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".doc",
    ".docx",
}

# Valid thread ID pattern
_VALID_THREAD_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


class UploadResponse(BaseModel):
    """Response model for file upload."""

    success: bool
    files: list[dict[str, Any]]
    message: str


def get_uploads_dir(thread_id: str) -> Path:
    """Get the uploads directory for a thread.

    Args:
        thread_id: The thread ID.

    Returns:
        Path to the uploads directory.
    """
    base_dir = get_paths().sandbox_uploads_dir(thread_id)
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


async def convert_file_to_markdown(file_path: Path) -> Path | None:
    """Convert a file to markdown using markitdown.

    Args:
        file_path: Path to the file to convert.

    Returns:
        Path to the markdown file if conversion was successful, None otherwise.
    """
    try:
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert(str(file_path))

        md_path = file_path.with_suffix(".md")
        await asyncio.to_thread(md_path.write_text, result.text_content, encoding="utf-8")

        logger.info("Converted %s to markdown: %s", file_path.name, md_path.name)
        return md_path
    except Exception as e:
        logger.error("Failed to convert %s to markdown: %s", file_path.name, e)
        return None


@router.post("", response_model=UploadResponse)
async def upload_files(
    thread_id: str,
    files: list[UploadFile] = File(...),
) -> UploadResponse:
    """Upload multiple files to a thread's uploads directory.

    For PDF, PPT, Excel, and Word files, they will be converted to markdown using markitdown.
    All files (original and converted) are saved to /mnt/user-data/uploads.

    Args:
        thread_id: The thread ID to upload files to.
        files: List of files to upload.

    Returns:
        Upload response with success status and file information.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if not _VALID_THREAD_ID_RE.match(thread_id):
        raise HTTPException(status_code=400, detail="Invalid thread ID format")

    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum {MAX_FILES_PER_UPLOAD} files per upload.",
        )

    uploads_dir = get_uploads_dir(thread_id)
    paths = get_paths()
    uploaded_files = []

    sandbox_provider = get_sandbox_provider()
    sandbox_id = sandbox_provider.acquire(thread_id)
    sandbox = sandbox_provider.get(sandbox_id)

    for file in files:
        if not file.filename:
            continue

        try:
            # Normalize filename to prevent path traversal
            safe_filename = Path(file.filename).name
            if not safe_filename or safe_filename in {".", ".."} or "/" in safe_filename or "\\" in safe_filename:
                logger.warning("Skipping file with unsafe filename: %r", file.filename)
                continue

            # Validate file extension
            file_ext = Path(safe_filename).suffix.lower()
            if file_ext not in ALLOWED_EXTENSIONS:
                logger.warning("Skipping file with disallowed extension: %s", safe_filename)
                continue

            content = await file.read()

            # Enforce file size limit
            if len(content) > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File '{safe_filename}' exceeds maximum size of {MAX_UPLOAD_SIZE // (1024 * 1024)} MB",
                )
            file_path = uploads_dir / safe_filename
            await asyncio.to_thread(file_path.write_bytes, content)

            # Build relative path from backend root
            relative_path = str(paths.sandbox_uploads_dir(thread_id) / safe_filename)
            virtual_path = f"{VIRTUAL_PATH_PREFIX}/uploads/{safe_filename}"

            # Keep local sandbox source of truth in thread-scoped host storage.
            # For non-local sandboxes, also sync to virtual path for runtime visibility.
            if sandbox_id != "local":
                sandbox.update_file(virtual_path, content)

            file_info = {
                "filename": safe_filename,
                "size": len(content),
                "path": relative_path,  # Actual filesystem path (relative to backend/)
                "virtual_path": virtual_path,  # Path for Agent in sandbox
                "artifact_url": f"/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/{safe_filename}",  # HTTP URL
            }

            logger.info("Saved file: %s (%d bytes) to %s", safe_filename, len(content), relative_path)

            # Check if file should be converted to markdown
            file_ext = file_path.suffix.lower()
            if file_ext in CONVERTIBLE_EXTENSIONS:
                md_path = await convert_file_to_markdown(file_path)
                if md_path:
                    md_relative_path = str(paths.sandbox_uploads_dir(thread_id) / md_path.name)
                    md_virtual_path = f"{VIRTUAL_PATH_PREFIX}/uploads/{md_path.name}"

                    if sandbox_id != "local":
                        sandbox.update_file(md_virtual_path, md_path.read_bytes())

                    file_info["markdown_file"] = md_path.name
                    file_info["markdown_path"] = md_relative_path
                    file_info["markdown_virtual_path"] = md_virtual_path
                    file_info["markdown_artifact_url"] = f"/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/{md_path.name}"

            uploaded_files.append(file_info)

        except Exception as e:
            logger.error("Failed to upload %s: %s", file.filename, e)
            raise HTTPException(status_code=500, detail=f"Failed to upload {file.filename}: {str(e)}")

    return UploadResponse(
        success=True,
        files=uploaded_files,
        message=f"Successfully uploaded {len(uploaded_files)} file(s)",
    )


@router.get("/list", response_model=dict)
async def list_uploaded_files(thread_id: str) -> dict:
    """List all files in a thread's uploads directory.

    Args:
        thread_id: The thread ID to list files for.

    Returns:
        Dictionary containing list of files with their metadata.
    """
    uploads_dir = get_uploads_dir(thread_id)

    if not uploads_dir.exists():
        return {"files": [], "count": 0}

    files = []
    for file_path in sorted(uploads_dir.iterdir()):
        if file_path.is_file():
            stat = file_path.stat()
            relative_path = str(get_paths().sandbox_uploads_dir(thread_id) / file_path.name)
            files.append(
                {
                    "filename": file_path.name,
                    "size": stat.st_size,
                    "path": relative_path,  # Actual filesystem path
                    "virtual_path": f"{VIRTUAL_PATH_PREFIX}/uploads/{file_path.name}",  # Path for Agent in sandbox
                    "artifact_url": f"/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/{file_path.name}",  # HTTP URL
                    "extension": file_path.suffix,
                    "modified": stat.st_mtime,
                }
            )

    return {"files": files, "count": len(files)}


@router.delete("/{filename}")
async def delete_uploaded_file(thread_id: str, filename: str) -> dict:
    """Delete a file from a thread's uploads directory.

    Args:
        thread_id: The thread ID.
        filename: The filename to delete.

    Returns:
        Success message.
    """
    uploads_dir = get_uploads_dir(thread_id)

    # Sanitize filename to prevent path traversal
    safe_filename = Path(filename).name
    if not safe_filename or safe_filename != filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = uploads_dir / safe_filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    # Security check: ensure the path is within the uploads directory
    try:
        file_path.resolve().relative_to(uploads_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        file_path.unlink()
        logger.info("Deleted file: %s", filename)
        return {"success": True, "message": f"Deleted {filename}"}
    except Exception as e:
        logger.error("Failed to delete %s: %s", safe_filename, e)
        raise HTTPException(status_code=500, detail="Failed to delete file")
