"""Audio transcription router — speech-to-text for uploaded audio files.

Uses faster-whisper (CTranslate2 backend) when available, falls back to
OpenAI Whisper API if OPENAI_API_KEY is set.  Browser-side voice input
uses the Web Speech API and sends text directly — this endpoint is for
audio *file* uploads (mp3, wav, m4a, ogg, webm).
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/transcribe", tags=["transcription"])

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac", ".aac"}
MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25 MB


class TranscriptionResponse(BaseModel):
    """Response model for audio transcription."""

    success: bool
    text: str
    language: str | None = None
    duration_seconds: float | None = None
    engine: str = "unknown"


async def _transcribe_with_faster_whisper(audio_path: Path) -> TranscriptionResponse:
    """Transcribe using faster-whisper (local, no API key needed)."""
    from faster_whisper import WhisperModel

    def _run():
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(audio_path), beam_size=5)
        text_parts = [seg.text for seg in segments]
        return " ".join(text_parts).strip(), info.language, info.duration

    text, lang, duration = await asyncio.to_thread(_run)
    return TranscriptionResponse(
        success=True,
        text=text,
        language=lang,
        duration_seconds=duration,
        engine="faster-whisper",
    )


async def _transcribe_with_openai(audio_path: Path) -> TranscriptionResponse:
    """Transcribe using OpenAI Whisper API."""
    import os

    import httpx

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    async with httpx.AsyncClient(timeout=120.0) as client:
        with open(audio_path, "rb") as f:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (audio_path.name, f, "audio/mpeg")},
                data={"model": "whisper-1", "response_format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()

    return TranscriptionResponse(
        success=True,
        text=data.get("text", ""),
        language=data.get("language"),
        duration_seconds=data.get("duration"),
        engine="openai-whisper",
    )


@router.post("", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
) -> TranscriptionResponse:
    """Transcribe an audio file to text.

    Accepts mp3, wav, m4a, ogg, webm, flac, aac files up to 25 MB.
    Uses faster-whisper locally if installed, otherwise falls back to
    OpenAI Whisper API.

    Args:
        file: Audio file to transcribe.

    Returns:
        Transcription result with text, language, and duration.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format: {suffix}. Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}",
        )

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large ({len(content)} bytes). Max: {MAX_AUDIO_SIZE} bytes (25 MB).",
        )

    # Write to temp file
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        # Try faster-whisper first
        try:
            return await _transcribe_with_faster_whisper(tmp_path)
        except ImportError:
            logger.info("faster-whisper not installed, trying OpenAI API")
        except Exception as exc:
            logger.warning(f"faster-whisper failed: {exc}, trying OpenAI API")

        # Try OpenAI Whisper API
        try:
            return await _transcribe_with_openai(tmp_path)
        except Exception as exc:
            logger.error(f"OpenAI transcription failed: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Transcription failed. Install faster-whisper or set OPENAI_API_KEY. Error: {exc}",
            ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)
