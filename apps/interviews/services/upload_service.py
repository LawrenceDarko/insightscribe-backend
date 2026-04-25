"""
InsightScribe - Interview Upload Service
Handles file validation, duplicate detection, S3 upload, and Interview record creation.
Automatically triggers async transcription after a successful upload.
"""

import logging
import os
from hashlib import sha256
from urllib.parse import parse_qs, urlparse

import tiktoken
from django.db import transaction
from django.utils import timezone

from apps.common.validators import compute_file_hash, validate_audio_file, validate_file_not_duplicate
from apps.transcription.models import TranscriptChunk

from ..models import Interview, ProcessingStatus, VALID_STATUS_TRANSITIONS
from .storage_service import generate_file_key, upload_file

logger = logging.getLogger("apps.interviews")

MAX_MANUAL_CHUNK_TOKENS = 500
MANUAL_CHUNK_OVERLAP_TOKENS = 50


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
def upload_interview(project, file, title="") -> tuple:
    """
    Full upload pipeline:
    1. Validate file (size, extension, magic-byte MIME)
    2. Compute content hash for duplicate detection
    3. Check for duplicates (hash + filename)
    4. Upload to S3
    5. Create Interview record with status = UPLOADED

    Returns (interview, None) on success, (None, error_message) on failure.
    """
    # 1. Validate
    is_valid, error_msg = validate_audio_file(file)
    if not is_valid:
        return None, error_msg

    # 2. Content hash
    file_hash = compute_file_hash(file)

    # 3. Duplicate check
    is_unique, dup_error = validate_file_not_duplicate(project, file_hash, file.name)
    if not is_unique:
        return None, dup_error

    # 4. Upload to S3
    file_key = generate_file_key(str(project.id), file.name)
    content_type = getattr(file, "content_type", "application/octet-stream")
    file_url, upload_error = upload_file(file, file_key, content_type)
    if upload_error:
        return None, upload_error

    # 5. Create record
    interview = Interview.objects.create(
        project=project,
        title=title or file.name,
        source_type="file",
        file_url=file_url,
        file_name=file.name,
        file_size=file.size,
        file_hash=file_hash,
        processing_status=ProcessingStatus.UPLOADED,
    )

    logger.info(
        "Interview uploaded: id=%s project=%s size=%s hash=%s",
        interview.id, project.id, file.size, file_hash[:12],
    )

    # 6. Dispatch async transcription (non-blocking — upload succeeds even if broker is down)
    try:
        from apps.transcription.tasks import transcribe_interview_task
        transcribe_interview_task.delay(str(interview.id))
        logger.info("Transcription task dispatched for interview %s", interview.id)
    except Exception as exc:
        logger.error("Failed to dispatch transcription task for %s: %s", interview.id, exc)

    return interview, None


def create_interview_from_link(project, media_url: str, title: str = "") -> tuple:
    """
    Register an interview backed by a directly downloadable audio/video URL.
    The regular async transcription pipeline is triggered immediately.
    """
    parsed = urlparse(media_url)
    inferred_name = _infer_media_filename(parsed) or "external-media.mp4"

    if Interview.objects.filter(project=project, file_url=media_url, is_deleted=False).exists():
        return None, "This media link has already been uploaded to this project."

    interview = Interview.objects.create(
        project=project,
        title=title or inferred_name,
        source_type="link",
        file_url=media_url,
        file_name=inferred_name,
        file_size=0,
        file_hash="",
        processing_status=ProcessingStatus.UPLOADED,
    )

    try:
        from apps.transcription.tasks import transcribe_interview_task
        transcribe_interview_task.delay(str(interview.id))
        logger.info("Transcription task dispatched for link interview %s", interview.id)
    except Exception as exc:
        logger.error("Failed to dispatch transcription task for %s: %s", interview.id, exc)

    return interview, None


def create_interview_from_transcript(project, transcript_text: str, title: str = "") -> tuple:
    """
    Create an interview from manual transcript text, chunk it, then queue embeddings.
    """
    cleaned = (transcript_text or "").strip()
    if not cleaned:
        return None, "Transcript text cannot be empty."

    text_hash = sha256(cleaned.encode("utf-8")).hexdigest()
    if Interview.objects.filter(project=project, file_hash=text_hash, is_deleted=False).exists():
        return None, "This transcript appears to be a duplicate of an existing interview."

    chunks = _split_manual_transcript(cleaned)
    if not chunks:
        return None, "Transcript text did not contain any processable content."

    with transaction.atomic():
        interview = Interview.objects.create(
            project=project,
            title=title or "Manual transcript",
            source_type="transcript",
            file_url="",
            file_name="manual-transcript.txt",
            file_size=len(cleaned.encode("utf-8")),
            file_hash=text_hash,
            processing_status=ProcessingStatus.EMBEDDING,
            processing_progress=0,
            duration_seconds=0,
        )

        TranscriptChunk.objects.bulk_create(
            [
                TranscriptChunk(
                    interview=interview,
                    text=chunk["text"],
                    start_time=0.0,
                    end_time=0.0,
                    chunk_index=idx,
                    speaker_label="",
                    token_count=chunk["token_count"],
                )
                for idx, chunk in enumerate(chunks)
            ]
        )

    try:
        from apps.embeddings.tasks import generate_embeddings_task
        generate_embeddings_task.delay(str(interview.id))
        logger.info("Embedding task dispatched for transcript interview %s", interview.id)
    except Exception as exc:
        logger.error("Failed to dispatch embedding task for %s: %s", interview.id, exc)

    return interview, None


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def get_project_interviews(project, include_deleted=False):
    """Return interviews for a project, optionally including soft-deleted."""
    qs = Interview.objects.filter(project=project)
    if not include_deleted:
        qs = qs.filter(is_deleted=False)
    return qs.order_by("-created_at")


def get_interview(interview_id, project):
    """Retrieve a single active interview within a project."""
    try:
        return Interview.objects.get(id=interview_id, project=project, is_deleted=False)
    except Interview.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------
def update_processing_status(interview, new_status, error="") -> tuple[bool, str | None]:
    """
    Safely transition interview processing status.
    Validates the transition against VALID_STATUS_TRANSITIONS.
    Returns (success, error_message).
    """
    if not interview.can_transition_to(new_status):
        msg = (
            f"Invalid status transition: {interview.processing_status} → {new_status}. "
            f"Allowed: {VALID_STATUS_TRANSITIONS.get(interview.processing_status, [])}"
        )
        logger.warning("Interview %s: %s", interview.id, msg)
        return False, msg

    update_fields = ["processing_status", "updated_at"]
    interview.processing_status = new_status

    # Reset progress on new phase; set 100 on terminal states
    if new_status in (ProcessingStatus.TRANSCRIBING, ProcessingStatus.EMBEDDING):
        interview.processing_progress = 0
        update_fields.append("processing_progress")
    elif new_status == ProcessingStatus.COMPLETE:
        interview.processing_progress = 100
        update_fields.append("processing_progress")
    elif new_status == ProcessingStatus.FAILED:
        # Keep the progress where it stopped
        pass

    if new_status == ProcessingStatus.TRANSCRIBING:
        interview.processing_started_at = timezone.now()
        update_fields.append("processing_started_at")
    elif new_status in (ProcessingStatus.COMPLETE, ProcessingStatus.FAILED):
        interview.processing_completed_at = timezone.now()
        update_fields.append("processing_completed_at")

    if error:
        interview.processing_error = error
        update_fields.append("processing_error")
    elif new_status != ProcessingStatus.FAILED:
        # Clear previous error on successful transition
        interview.processing_error = ""
        update_fields.append("processing_error")

    interview.save(update_fields=update_fields)
    logger.info("Interview %s status → %s", interview.id, new_status)
    return True, None


def update_processing_progress(interview, progress: int) -> None:
    """
    Lightweight progress update (0–100). Skips validation for speed.
    Only writes the two columns that changed.
    """
    progress = max(0, min(100, progress))
    interview.processing_progress = progress
    interview.save(update_fields=["processing_progress", "updated_at"])


def mark_for_reprocessing(interview) -> tuple[bool, str | None]:
    """
    Reset a failed interview back to UPLOADED so it re-enters the pipeline.
    Only valid from FAILED status.
    """
    if interview.processing_status != ProcessingStatus.FAILED:
        return False, "Only failed interviews can be reprocessed."

    interview.processing_status = ProcessingStatus.UPLOADED
    interview.processing_error = ""
    interview.processing_started_at = None
    interview.processing_completed_at = None
    interview.save(update_fields=[
        "processing_status", "processing_error",
        "processing_started_at", "processing_completed_at", "updated_at",
    ])
    logger.info("Interview %s marked for reprocessing", interview.id)
    return True, None


def _split_manual_transcript(text: str) -> list[dict]:
    """Split transcript text into token-bounded chunks for embedding safety."""
    encoder = tiktoken.encoding_for_model("gpt-4o")
    tokens = encoder.encode(text)
    if not tokens:
        return []

    chunks = []
    idx = 0
    step = max(MAX_MANUAL_CHUNK_TOKENS - MANUAL_CHUNK_OVERLAP_TOKENS, 1)

    while idx < len(tokens):
        window = tokens[idx: idx + MAX_MANUAL_CHUNK_TOKENS]
        chunk_text = encoder.decode(window).strip()
        if chunk_text:
            chunks.append({"text": chunk_text, "token_count": len(window)})
        idx += step

    return chunks


def _infer_media_filename(parsed_url) -> str:
    """Try to infer a file-like name from URL path or common query params."""
    from_path = os.path.basename(parsed_url.path)
    if from_path and "." in from_path:
        return from_path

    query = parse_qs(parsed_url.query)
    for key in ("filename", "file", "name"):
        values = query.get(key, [])
        if values:
            candidate = values[0].strip()
            if candidate and "." in candidate:
                return candidate

    return ""
