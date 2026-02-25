"""
InsightScribe - S3 Storage Service
Encapsulates all Supabase Storage (S3-compatible) interactions.
Uses a module-level client singleton to avoid reconnecting on every request.
"""

import logging
import uuid

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger("apps.interviews")

# ---------------------------------------------------------------------------
# Module-level S3 client (lazy singleton)
# ---------------------------------------------------------------------------
_s3_client = None


def _get_s3_client():
    """Return a reusable boto3 S3 client configured for Supabase Storage."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            region_name=settings.AWS_S3_REGION_NAME,
            config=BotoConfig(
                signature_version=settings.AWS_S3_SIGNATURE_VERSION,
                retries={"max_attempts": 3, "mode": "adaptive"},
                connect_timeout=10,
                read_timeout=60,
            ),
        )
    return _s3_client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_file_key(project_id: str, filename: str) -> str:
    """Generate a unique, collision-free S3 object key."""
    unique = uuid.uuid4().hex[:16]
    # Sanitize the filename (keep only the safe portion)
    safe_name = filename.replace(" ", "_").replace("/", "_")
    return f"interviews/{project_id}/{unique}_{safe_name}"


def upload_file(file, file_key: str, content_type: str = "application/octet-stream") -> tuple[str | None, str | None]:
    """
    Upload an InMemory/Temporary uploaded file to S3-compatible storage.

    Returns (file_url, None) on success, (None, error_message) on failure.
    """
    client = _get_s3_client()
    bucket = settings.AWS_STORAGE_BUCKET_NAME

    try:
        file.seek(0)
        client.upload_fileobj(
            file,
            bucket,
            file_key,
            ExtraArgs={
                "ContentType": content_type,
                "CacheControl": "private, max-age=0, no-cache",
            },
        )
        file_url = f"{settings.AWS_S3_ENDPOINT_URL}/{bucket}/{file_key}"
        return file_url, None
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        logger.error("S3 upload failed [%s]: %s", error_code, exc)
        return None, f"Storage upload failed ({error_code}). Please try again."
    except Exception as exc:
        logger.error("Unexpected S3 upload error: %s", exc)
        return None, "Storage upload failed. Please try again."


def delete_file(file_key: str) -> bool:
    """Delete an object from S3. Returns True on success."""
    client = _get_s3_client()
    try:
        client.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=file_key)
        return True
    except Exception as exc:
        logger.error("S3 delete failed for key %s: %s", file_key, exc)
        return False


def generate_presigned_url(file_key: str, expires_in: int = 3600) -> str | None:
    """Generate a pre-signed download URL. Returns None on failure."""
    client = _get_s3_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": file_key},
            ExpiresIn=expires_in,
        )
    except Exception as exc:
        logger.error("Failed to generate presigned URL for %s: %s", file_key, exc)
        return None
