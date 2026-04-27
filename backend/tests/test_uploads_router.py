import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from src.config.paths import Paths
from src.gateway.routers import uploads


class FakeSandboxProvider:
    def acquire(self, thread_id: str) -> str:
        return "local"

    def get(self, sandbox_id: str):
        return object()


def make_upload(filename: str, content: bytes = b"hello") -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=filename)


@pytest.fixture(autouse=True)
def isolated_upload_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(uploads, "get_paths", lambda: Paths(tmp_path / "workspace"))
    monkeypatch.setattr(uploads, "get_sandbox_provider", lambda: FakeSandboxProvider())


def test_upload_rejects_invalid_thread_id():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(uploads.upload_files("../bad", [make_upload("note.txt")]))

    assert exc_info.value.status_code == 400


def test_upload_skips_backslash_path_filename(tmp_path):
    response = asyncio.run(
        uploads.upload_files("thread-a", [make_upload(r"nested\secret.txt")])
    )

    assert response.success is True
    assert response.files == []
    assert not list((tmp_path / "workspace").rglob("secret.txt"))


def test_upload_path_traversal_filename_is_sandboxed_to_thread_uploads(tmp_path):
    response = asyncio.run(
        uploads.upload_files("thread-a", [make_upload("../secret.txt", b"secret")])
    )

    uploads_dir = tmp_path / "workspace" / "default" / "threads" / "thread-a" / "uploads"
    assert response.success is True
    assert response.files[0]["filename"] == "secret.txt"
    assert (uploads_dir / "secret.txt").read_bytes() == b"secret"
    assert not (tmp_path / "workspace" / "default" / "threads" / "secret.txt").exists()


def test_convertible_upload_keeps_original_when_markdown_conversion_fails(monkeypatch, tmp_path):
    async def fail_conversion(_path):
        return None

    monkeypatch.setattr(uploads, "convert_file_to_markdown", fail_conversion)

    response = asyncio.run(
        uploads.upload_files("thread-a", [make_upload("report.docx", b"docx")])
    )

    uploads_dir = tmp_path / "workspace" / "default" / "threads" / "thread-a" / "uploads"
    assert response.success is True
    assert response.files[0]["filename"] == "report.docx"
    assert "markdown_file" not in response.files[0]
    assert (uploads_dir / "report.docx").read_bytes() == b"docx"


def test_uploads_are_thread_isolated(tmp_path):
    asyncio.run(uploads.upload_files("thread-a", [make_upload("same.txt", b"a")]))
    asyncio.run(uploads.upload_files("thread-b", [make_upload("same.txt", b"b")]))

    thread_a = tmp_path / "workspace" / "default" / "threads" / "thread-a" / "uploads" / "same.txt"
    thread_b = tmp_path / "workspace" / "default" / "threads" / "thread-b" / "uploads" / "same.txt"
    assert thread_a.read_bytes() == b"a"
    assert thread_b.read_bytes() == b"b"
