"""
InsightScribe - Embedding Generation Service
Production-grade pipeline: fetch chunks → batch embed via OpenAI → bulk-store
in pgvector → advance interview status.

Designed to run inside a Celery worker.  All OpenAI calls include retry logic
with exponential back-off for transient errors.
"""

import logging
import time
from typing import List

from django.conf import settings
from django.db import transaction
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from apps.interviews.models import ProcessingStatus
from apps.interviews.services.upload_service import update_processing_progress, update_processing_status
from apps.transcription.models import TranscriptChunk

from ..models import Embedding

logger = logging.getLogger("apps.embeddings")

# ---------------------------------------------------------------------------
# Configuration (overridable via settings / env)
# ---------------------------------------------------------------------------
EMBEDDING_BATCH_SIZE: int = getattr(settings, "EMBEDDING_BATCH_SIZE", 100)
EMBEDDING_MAX_RETRIES: int = getattr(settings, "EMBEDDING_MAX_RETRIES", 3)
EMBEDDING_RETRY_BASE_DELAY: float = getattr(settings, "EMBEDDING_RETRY_BASE_DELAY", 2.0)

# Retriable OpenAI exceptions
_RETRIABLE = (APIConnectionError, APITimeoutError, RateLimitError)

# Module-level OpenAI client (lazy singleton — avoids re-creation per batch)
_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


# ============================================================================
# Public: generate embeddings for an interview
# ============================================================================
def generate_embeddings_for_interview(interview) -> bool:
    """
    Full embedding pipeline:
    1. Transition status → ``embedding``
    2. Fetch un-embedded transcript chunks (avoids N+1 via query)
    3. Delete stale embeddings for this interview (idempotent re-embed)
    4. Batch-generate embeddings via OpenAI (with retries)
    5. Bulk-create Embedding records
    6. Transition status → ``complete``

    Returns ``True`` on success, ``False`` on failure.
    """
    pipeline_start = time.monotonic()
    logger.info("Embedding pipeline START — interview=%s", interview.id)

    # 1. Status → embedding (skip if already there — transcription pipeline
    #    sets this before dispatching the embedding task)
    if interview.processing_status != ProcessingStatus.EMBEDDING:
        ok, err = update_processing_status(interview, ProcessingStatus.EMBEDDING)
        if not ok:
            logger.error("Cannot start embedding for %s: %s", interview.id, err)
            return False

    try:
        # 2. Fetch chunks to embed
        chunks = list(
            TranscriptChunk.objects.filter(
                interview=interview,
                is_deleted=False,
            )
            .order_by("chunk_index")
            .only("id", "interview_id", "text", "chunk_index", "token_count")
        )

        if not chunks:
            logger.warning("No chunks found for interview %s — marking complete", interview.id)
            update_processing_status(interview, ProcessingStatus.COMPLETE)
            return True

        # 3. Delete stale embeddings (atomic with re-creation)
        with transaction.atomic():
            deleted_count, _ = Embedding.objects.filter(interview=interview).delete()
            if deleted_count:
                logger.info("Deleted %d stale embeddings for interview %s", deleted_count, interview.id)

        # 4 + 5. Batch embed and persist
        total_created = 0
        for batch_start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[batch_start : batch_start + EMBEDDING_BATCH_SIZE]
            texts = [chunk.text for chunk in batch]

            vectors = _generate_batch_embeddings_with_retries(texts)
            if vectors is None:
                _fail(interview, "Embedding API failed after retries.")
                return False

            embedding_objects = [
                Embedding(
                    transcript_chunk=chunk,
                    interview=interview,
                    vector=vector,
                    model_name=settings.OPENAI_EMBEDDING_MODEL,
                )
                for chunk, vector in zip(batch, vectors)
            ]

            with transaction.atomic():
                Embedding.objects.bulk_create(embedding_objects, batch_size=EMBEDDING_BATCH_SIZE)

            total_created += len(embedding_objects)
            # Update progress proportionally (5–95% of embedding phase)
            pct = int(5 + (total_created / len(chunks)) * 90)
            update_processing_progress(interview, min(pct, 95))
            logger.info(
                "Batch %d–%d embedded (%d/%d) — interview=%s",
                batch_start, batch_start + len(batch), total_created, len(chunks), interview.id,
            )

        # 6. Status → complete
        update_processing_progress(interview, 100)
        update_processing_status(interview, ProcessingStatus.COMPLETE)

        elapsed = time.monotonic() - pipeline_start
        logger.info(
            "Embedding pipeline DONE — interview=%s vectors=%d elapsed=%.2fs",
            interview.id, total_created, elapsed,
        )
        return True

    except Exception as exc:
        elapsed = time.monotonic() - pipeline_start
        logger.exception(
            "Embedding pipeline FAILED — interview=%s elapsed=%.2fs error=%s",
            interview.id, elapsed, exc,
        )
        _fail(interview, str(exc))
        return False


# ============================================================================
# Public: single query embedding
# ============================================================================
def generate_query_embedding(text: str) -> list[float]:
    """
    Generate a single embedding vector for a search query.
    Uses the same retry logic as batch generation.
    """
    vectors = _generate_batch_embeddings_with_retries([text])
    if vectors is None or len(vectors) == 0:
        raise RuntimeError("Failed to generate query embedding.")
    return vectors[0]


# ============================================================================
# Public: similarity search
# ============================================================================
def similarity_search(
    query_vector: list[float],
    project_id,
    top_k: int = 10,
    score_threshold: float | None = None,
) -> list[dict]:
    """
    Perform cosine similarity search across all transcript chunks in a project.

    Uses pgvector's ``CosineDistance`` operator with the HNSW index.
    Leverages the denormalized ``interview`` FK to avoid a 3-table JOIN.

    Args:
        query_vector: The embedding vector for the search query.
        project_id: UUID of the project to search within.
        top_k: Maximum number of results to return.
        score_threshold: Optional minimum similarity score (0–1). Results below
            this threshold are excluded.

    Returns:
        List of dicts with chunk data, interview metadata, and similarity score.
    """
    from pgvector.django import CosineDistance

    qs = (
        Embedding.objects.filter(
            interview__project_id=project_id,
            interview__is_deleted=False,
            transcript_chunk__is_deleted=False,
        )
        .annotate(distance=CosineDistance("vector", query_vector))
        .order_by("distance")
        .select_related("transcript_chunk", "interview")
    )

    # Optional score filter (distance = 1 - similarity)
    if score_threshold is not None:
        max_distance = 1.0 - score_threshold
        qs = qs.filter(distance__lte=max_distance)

    results = qs[:top_k]

    return [
        {
            "chunk_id": str(r.transcript_chunk_id),
            "interview_id": str(r.interview_id),
            "interview_title": r.interview.title,
            "text": r.transcript_chunk.text,
            "start_time": r.transcript_chunk.start_time,
            "end_time": r.transcript_chunk.end_time,
            "chunk_index": r.transcript_chunk.chunk_index,
            "speaker_label": r.transcript_chunk.speaker_label,
            "token_count": r.transcript_chunk.token_count,
            "similarity": round(1.0 - r.distance, 4),
        }
        for r in results
    ]


# ============================================================================
# Public: embedding stats for an interview
# ============================================================================
def get_embedding_stats(interview) -> dict:
    """Return summary statistics about embeddings for a given interview."""
    from django.db.models import Count

    total_chunks = TranscriptChunk.objects.filter(
        interview=interview, is_deleted=False,
    ).count()
    embedded_chunks = Embedding.objects.filter(interview=interview).count()

    return {
        "interview_id": str(interview.id),
        "total_chunks": total_chunks,
        "embedded_chunks": embedded_chunks,
        "coverage_pct": round((embedded_chunks / total_chunks * 100) if total_chunks else 0, 1),
        "model_name": settings.OPENAI_EMBEDDING_MODEL,
        "dimensions": settings.OPENAI_EMBEDDING_DIMENSIONS,
    }


# ============================================================================
# Internal: batch embeddings with retry
# ============================================================================
def _generate_batch_embeddings_with_retries(texts: list[str]) -> list[list[float]] | None:
    """
    Generate embeddings for a batch of texts via OpenAI API.
    Retries on transient errors with exponential back-off.
    Returns ``None`` on exhausted retries.
    """
    client = _get_openai_client()

    for attempt in range(1, EMBEDDING_MAX_RETRIES + 1):
        try:
            call_start = time.monotonic()
            response = client.embeddings.create(
                model=settings.OPENAI_EMBEDDING_MODEL,
                input=texts,
                dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
            )
            call_elapsed = time.monotonic() - call_start

            # Sort by index to maintain input order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            vectors = [item.embedding for item in sorted_data]

            logger.debug(
                "Embedding API: %d texts in %.2fs (attempt %d)",
                len(texts), call_elapsed, attempt,
            )
            return vectors

        except _RETRIABLE as exc:
            delay = EMBEDDING_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "Embedding transient error (attempt %d/%d), retrying in %.1fs: %s",
                attempt, EMBEDDING_MAX_RETRIES, delay, exc,
            )
            if attempt < EMBEDDING_MAX_RETRIES:
                time.sleep(delay)
            else:
                logger.error("Embedding API exhausted all %d retries", EMBEDDING_MAX_RETRIES)
                return None

        except Exception as exc:
            logger.error("Embedding API non-retriable error: %s", exc)
            raise

    return None  # pragma: no cover


# ============================================================================
# Internal helpers
# ============================================================================
def _fail(interview, error_msg: str):
    """Convenience: mark interview as failed with an error message."""
    update_processing_status(interview, ProcessingStatus.FAILED, error=error_msg)
