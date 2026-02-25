"""
InsightScribe - Whisper Transcription Service
Production-grade pipeline: download from S3 → Whisper API → chunk → bulk-save.

This module is designed to run inside a Celery worker, **never** in the
request cycle.  All OpenAI calls include retry logic with exponential backoff.
"""

import io
import logging
import tempfile
import time
from urllib.parse import urlparse

import tiktoken
from django.conf import settings
from django.db import transaction
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from apps.interviews.models import ProcessingStatus
from apps.interviews.services.storage_service import _get_s3_client
from apps.interviews.services.upload_service import update_processing_progress, update_processing_status

from ..models import TranscriptChunk

logger = logging.getLogger("apps.transcription")

# ---------------------------------------------------------------------------
# Chunking configuration
# ---------------------------------------------------------------------------
MAX_CHUNK_TOKENS: int = getattr(settings, "TRANSCRIPTION_MAX_CHUNK_TOKENS", 500)
OVERLAP_TOKENS: int = getattr(settings, "TRANSCRIPTION_OVERLAP_TOKENS", 50)

# ---------------------------------------------------------------------------
# Whisper retry configuration
# ---------------------------------------------------------------------------
WHISPER_MAX_RETRIES: int = getattr(settings, "WHISPER_MAX_RETRIES", 3)
WHISPER_RETRY_BASE_DELAY: float = getattr(settings, "WHISPER_RETRY_BASE_DELAY", 2.0)

# Retriable OpenAI exceptions
_RETRIABLE_EXCEPTIONS = (APIConnectionError, APITimeoutError, RateLimitError)


# ============================================================================
# Public entry point
# ============================================================================
def transcribe_interview(interview) -> bool:
    """
    Full transcription pipeline:
    1. Transition status → ``transcribing``
    2. Download audio from S3 into a temp file
    3. Call Whisper API (with retries)
    4. Parse response into token-bounded chunks
    5. Delete old chunks (idempotent re-transcription) + bulk-create new ones
    6. Update interview duration
    7. Transition status → ``embedding`` (next pipeline stage)

    Returns ``True`` on success, ``False`` on failure.
    """
    pipeline_start = time.monotonic()
    logger.info("Transcription pipeline START — interview=%s", interview.id)

    # 1. Status → transcribing
    ok, err = update_processing_status(interview, ProcessingStatus.TRANSCRIBING)
    if not ok:
        logger.error("Cannot start transcription for %s: %s", interview.id, err)
        return False

    try:
        # 2. Download audio from S3
        update_processing_progress(interview, 5)
        audio_bytes = _download_from_s3(interview.file_url)
        if audio_bytes is None:
            _fail(interview, "Failed to download audio from storage.")
            return False
        update_processing_progress(interview, 15)

        # 3. Whisper API
        transcript_data = _call_whisper_with_retries(audio_bytes, interview.file_name)
        if transcript_data is None:
            _fail(interview, "Whisper API returned no data after retries.")
            return False
        update_processing_progress(interview, 60)

        # 4. Chunk
        chunks = _split_into_chunks(transcript_data)
        if not chunks:
            _fail(interview, "Transcription produced no usable text.")
            return False
        update_processing_progress(interview, 75)

        # 5. Persist (atomic: delete old + create new)
        _persist_chunks(interview, chunks)
        update_processing_progress(interview, 90)

        # 6. Duration
        if transcript_data.get("duration"):
            interview.duration_seconds = transcript_data["duration"]
            interview.save(update_fields=["duration_seconds", "updated_at"])

        # 7. Advance status → embedding
        update_processing_progress(interview, 100)
        update_processing_status(interview, ProcessingStatus.EMBEDDING)

        elapsed = time.monotonic() - pipeline_start
        logger.info(
            "Transcription pipeline DONE — interview=%s chunks=%d duration=%.2fs",
            interview.id, len(chunks), elapsed,
        )
        return True

    except Exception as exc:
        elapsed = time.monotonic() - pipeline_start
        logger.exception(
            "Transcription pipeline FAILED — interview=%s elapsed=%.2fs error=%s",
            interview.id, elapsed, exc,
        )
        _fail(interview, str(exc))
        return False


# ============================================================================
# S3 download
# ============================================================================
def _download_from_s3(file_url: str) -> bytes | None:
    """
    Download the audio file from Supabase S3 storage into memory.
    Falls back to streaming the full object into a bytes buffer.
    """
    try:
        s3 = _get_s3_client()
        bucket = settings.AWS_STORAGE_BUCKET_NAME

        # Extract the S3 key from the full URL.
        # URL format: <endpoint>/<bucket>/<key>
        # The endpoint itself may have a path component (e.g. /storage/v1/s3),
        # so strip the endpoint prefix first, then the bucket name.
        endpoint_path = urlparse(settings.AWS_S3_ENDPOINT_URL).path.rstrip("/")
        parsed = urlparse(file_url)
        path = parsed.path

        # Remove the endpoint path prefix (e.g. "/storage/v1/s3")
        if endpoint_path and path.startswith(endpoint_path):
            path = path[len(endpoint_path):]

        path = path.lstrip("/")

        # Remove the bucket prefix
        if path.startswith(f"{bucket}/"):
            file_key = path[len(f"{bucket}/"):]
        else:
            file_key = path

        buf = io.BytesIO()
        s3.download_fileobj(bucket, file_key, buf)
        buf.seek(0)
        size = buf.getbuffer().nbytes
        logger.info("Downloaded %s from S3 (%.2f MB)", file_key, size / (1024 * 1024))
        return buf.getvalue()

    except Exception as exc:
        logger.error("S3 download failed for %s: %s", file_url, exc)
        return None


# ============================================================================
# Whisper API
# ============================================================================
def _call_whisper_with_retries(audio_bytes: bytes, file_name: str) -> dict | None:
    """
    Call Whisper with exponential-backoff retry for transient errors.
    Writes audio to a named temp file because OpenAI SDK requires a file-like
    object with a ``.name`` attribute ending in a supported extension.
    """
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    # Determine a safe suffix for the temp file
    suffix = _extract_extension(file_name) or ".mp3"

    for attempt in range(1, WHISPER_MAX_RETRIES + 1):
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp.flush()
            tmp_path = tmp.name

            try:
                logger.info("Whisper API call attempt %d/%d (%s)", attempt, WHISPER_MAX_RETRIES, file_name)
                call_start = time.monotonic()

                with open(tmp_path, "rb") as audio_file:
                    response = client.audio.transcriptions.create(
                        model=settings.OPENAI_WHISPER_MODEL,
                        file=audio_file,
                        response_format="verbose_json",
                        timestamp_granularities=["segment"],
                    )
            finally:
                import os
                os.unlink(tmp_path)

            call_elapsed = time.monotonic() - call_start
            logger.info("Whisper API responded in %.2fs", call_elapsed)

            return {
                "text": response.text,
                "segments": getattr(response, "segments", []) or [],
                "duration": getattr(response, "duration", None),
                "language": getattr(response, "language", None),
            }

        except _RETRIABLE_EXCEPTIONS as exc:
            delay = WHISPER_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "Whisper transient error (attempt %d/%d), retrying in %.1fs: %s",
                attempt, WHISPER_MAX_RETRIES, delay, exc,
            )
            if attempt < WHISPER_MAX_RETRIES:
                time.sleep(delay)
            else:
                logger.error("Whisper API exhausted all %d retries", WHISPER_MAX_RETRIES)
                raise

        except Exception:
            # Non-retriable errors bubble up immediately
            raise

    return None  # pragma: no cover — safety fallback


def _extract_extension(file_name: str) -> str:
    """Return file extension including the dot, e.g. '.mp3'."""
    import os
    _, ext = os.path.splitext(file_name)
    return ext.lower() if ext else ""


# ============================================================================
# Chunk splitting
# ============================================================================
def _split_into_chunks(transcript_data: dict) -> list[dict]:
    """
    Split Whisper segments into appropriately-sized chunks bounded by
    ``MAX_CHUNK_TOKENS``.  Falls back to pure-text splitting when no
    segments are present.
    """
    encoder = tiktoken.encoding_for_model("gpt-4o")
    segments = transcript_data.get("segments") or []

    if not segments:
        text = (transcript_data.get("text") or "").strip()
        if not text:
            return []
        return _split_text_by_tokens(text, encoder)

    chunks: list[dict] = []
    current_text = ""
    current_start = 0.0
    current_end = 0.0
    current_tokens = 0

    for segment in segments:
        seg_text = (getattr(segment, "text", None) or "").strip()
        if not seg_text:
            continue

        seg_tokens = len(encoder.encode(seg_text))
        seg_start = float(getattr(segment, "start", current_end))
        seg_end = float(getattr(segment, "end", seg_start))

        # Would adding this segment exceed the limit?
        if current_tokens + seg_tokens > MAX_CHUNK_TOKENS and current_text:
            chunks.append({
                "text": current_text.strip(),
                "start_time": current_start,
                "end_time": current_end,
                "token_count": current_tokens,
            })
            # Start new chunk (no overlap for segment-level splitting — overlap
            # is only used in the token-based fallback to preserve context).
            current_text = seg_text
            current_start = seg_start
            current_end = seg_end
            current_tokens = seg_tokens
        else:
            if not current_text:
                current_start = seg_start
            current_text += " " + seg_text
            current_end = seg_end
            current_tokens += seg_tokens

    # Flush remaining
    if current_text.strip():
        chunks.append({
            "text": current_text.strip(),
            "start_time": current_start,
            "end_time": current_end,
            "token_count": current_tokens,
        })

    return chunks


def _split_text_by_tokens(text: str, encoder) -> list[dict]:
    """Fallback: split plain text into token-bounded chunks with overlap."""
    tokens = encoder.encode(text)
    chunks: list[dict] = []
    idx = 0
    step = max(MAX_CHUNK_TOKENS - OVERLAP_TOKENS, 1)

    while idx < len(tokens):
        chunk_tokens = tokens[idx : idx + MAX_CHUNK_TOKENS]
        chunk_text = encoder.decode(chunk_tokens)
        chunks.append({
            "text": chunk_text,
            "start_time": 0.0,
            "end_time": 0.0,
            "token_count": len(chunk_tokens),
        })
        idx += step

    return chunks


# ============================================================================
# Persistence
# ============================================================================
def _persist_chunks(interview, chunks: list[dict]) -> int:
    """
    Atomically replace any existing chunks and bulk-create the new ones.
    Returns the number of chunks saved.
    """
    with transaction.atomic():
        # Delete previous chunks (idempotent re-transcription)
        deleted_count, _ = TranscriptChunk.objects.filter(interview=interview).delete()
        if deleted_count:
            logger.info("Deleted %d old chunks for interview %s", deleted_count, interview.id)

        chunk_objects = [
            TranscriptChunk(
                interview=interview,
                text=chunk["text"],
                start_time=chunk["start_time"],
                end_time=chunk["end_time"],
                chunk_index=idx,
                token_count=chunk.get("token_count", 0),
            )
            for idx, chunk in enumerate(chunks)
        ]
        TranscriptChunk.objects.bulk_create(chunk_objects, batch_size=500)

    logger.info("Saved %d chunks for interview %s", len(chunk_objects), interview.id)
    return len(chunk_objects)


# ============================================================================
# Internal helpers
# ============================================================================
def _fail(interview, error_msg: str):
    """Convenience: mark interview as failed with an error message."""
    update_processing_status(interview, ProcessingStatus.FAILED, error=error_msg)
