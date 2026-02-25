"""
InsightScribe - File Validation Utilities
Production-grade validators with magic-byte MIME detection and content-hash support.
"""

import hashlib
import mimetypes
import os

from django.conf import settings


# ---------------------------------------------------------------------------
# Magic bytes for supported audio/video formats
# ---------------------------------------------------------------------------
_MAGIC_SIGNATURES = {
    # MP3: ID3 tag or MPEG sync word
    b"ID3": "audio/mpeg",
    b"\xff\xfb": "audio/mpeg",
    b"\xff\xf3": "audio/mpeg",
    b"\xff\xf2": "audio/mpeg",
    # WAV: RIFF header
    b"RIFF": "audio/wav",
    # MP4 / M4A: ftyp atom (appears at byte 4)
    b"ftyp": "video/mp4",
}


def _detect_mime_from_magic(file) -> str | None:
    """
    Read the first 12 bytes of a file to determine MIME type from magic bytes.
    Resets the file pointer after reading.
    """
    try:
        header = file.read(12)
        file.seek(0)
    except Exception:
        return None

    if not header:
        return None

    # Standard prefix checks
    for signature, mime in _MAGIC_SIGNATURES.items():
        if header.startswith(signature):
            return mime

    # MP4 ftyp atom starts at byte 4
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return "video/mp4"

    return None


def compute_file_hash(file, algorithm: str = "sha256", chunk_size: int = 8192) -> str:
    """
    Compute a hex digest hash of an uploaded file without loading it fully into memory.
    Resets the file pointer after reading.
    """
    hasher = hashlib.new(algorithm)
    file.seek(0)
    while True:
        chunk = file.read(chunk_size)
        if not chunk:
            break
        hasher.update(chunk)
    file.seek(0)
    return hasher.hexdigest()


def validate_audio_file(file) -> tuple[bool, str | None]:
    """
    Validate uploaded audio file for:
    1. Non-empty file
    2. File size within configured limit
    3. File extension in allowed list
    4. MIME type (from Content-Type header, guessed from name, AND magic bytes)

    Returns (is_valid, error_message).
    """
    # 1. Non-empty
    if not file or file.size == 0:
        return False, "Uploaded file is empty."

    # 2. File size
    max_bytes = getattr(settings, "MAX_UPLOAD_SIZE_BYTES", 200 * 1024 * 1024)
    max_mb = getattr(settings, "MAX_UPLOAD_SIZE_MB", 200)
    if file.size > max_bytes:
        return False, f"File size ({file.size / (1024 * 1024):.1f}MB) exceeds the {max_mb}MB limit."

    # 3. Extension
    _, ext = os.path.splitext(file.name)
    ext_lower = ext.lower()
    allowed_extensions = getattr(settings, "ALLOWED_AUDIO_EXTENSIONS", [".mp3", ".wav", ".mp4"])
    if ext_lower not in allowed_extensions:
        return False, f"Invalid file extension '{ext}'. Allowed: {', '.join(allowed_extensions)}."

    # 4a. MIME type from Content-Type / guessed from name
    guessed_mime, _ = mimetypes.guess_type(file.name)
    header_mime = getattr(file, "content_type", None)
    allowed_types = getattr(settings, "ALLOWED_AUDIO_TYPES", [])

    # 4b. Magic-byte detection (most reliable)
    magic_mime = _detect_mime_from_magic(file)

    # Accept if at least one reliable source matches
    trusted_mimes = {m for m in (header_mime, guessed_mime, magic_mime) if m}

    if not trusted_mimes.intersection(allowed_types):
        reported = header_mime or guessed_mime or "unknown"
        return False, (
            f"Invalid file type '{reported}'. "
            f"Allowed: {', '.join(allowed_types)}."
        )

    return True, None


def validate_file_not_duplicate(project, file_hash: str, file_name: str) -> tuple[bool, str | None]:
    """
    Check that neither the same content hash nor the same filename already exists
    as an active (non-deleted) interview in the project.
    Returns (is_unique, error_message).
    """
    from apps.interviews.models import Interview

    # Hash-based duplicate detection (catches renamed re-uploads)
    if Interview.objects.filter(
        project=project,
        file_hash=file_hash,
        is_deleted=False,
    ).exists():
        return False, "This file has already been uploaded to this project (duplicate content detected)."

    # Name-based duplicate detection
    if Interview.objects.filter(
        project=project,
        file_name=file_name,
        is_deleted=False,
    ).exists():
        return False, f"A file named '{file_name}' already exists in this project."

    return True, None
