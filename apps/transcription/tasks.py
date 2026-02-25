"""
InsightScribe - Transcription Celery Tasks
Async background tasks for audio transcription via OpenAI Whisper.

Design notes:
- ``acks_late=True`` so the message is only acknowledged after the task
  finishes; if the worker crashes the task is redelivered.
- ``reject_on_worker_lost=True`` to requeue if the worker process is killed.
- Exponential back-off on retries (60 → 120 → 240 s).
- Idempotent: re-running will delete old chunks before creating new ones.
"""

import logging
import time

from celery import shared_task

from apps.interviews.models import Interview, ProcessingStatus
from apps.interviews.services.upload_service import update_processing_status

logger = logging.getLogger("apps.transcription")


@shared_task(
    bind=True,
    name="transcription.transcribe_interview",
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=600,
    acks_late=True,
    reject_on_worker_lost=True,
    track_started=True,
    time_limit=30 * 60,      # hard kill after 30 min
    soft_time_limit=25 * 60,  # SoftTimeLimitExceeded after 25 min
)
def transcribe_interview_task(self, interview_id: str):
    """
    Celery task: transcribe an uploaded interview.

    Called with ``transcribe_interview_task.delay(str(interview.id))``.
    """
    task_start = time.monotonic()
    logger.info("Task START — interview=%s task_id=%s attempt=%d", interview_id, self.request.id, self.request.retries + 1)

    # ---- Fetch interview ----
    try:
        interview = Interview.objects.get(id=interview_id)
    except Interview.DoesNotExist:
        logger.error("Interview not found, aborting: %s", interview_id)
        return {"status": "error", "detail": "Interview not found."}

    # ---- Guard: only process if in an expected state ----
    if interview.processing_status not in (
        ProcessingStatus.UPLOADED,
        ProcessingStatus.FAILED,
        ProcessingStatus.TRANSCRIBING,  # re-delivery after crash
    ):
        logger.warning(
            "Skipping transcription — interview %s is in '%s' state",
            interview_id, interview.processing_status,
        )
        return {"status": "skipped", "detail": f"Interview is in '{interview.processing_status}' state."}

    # ---- Run pipeline ----
    # Import here to avoid circular imports at module load time
    from .services.whisper_service import transcribe_interview

    try:
        success = transcribe_interview(interview)
    except Exception as exc:
        elapsed = time.monotonic() - task_start
        logger.error(
            "Task FAILED — interview=%s elapsed=%.2fs retries=%d error=%s",
            interview_id, elapsed, self.request.retries, exc,
        )
        # Mark as failed before retrying so the user sees the error
        update_processing_status(interview, ProcessingStatus.FAILED, error=str(exc))
        raise self.retry(exc=exc)

    elapsed = time.monotonic() - task_start
    if success:
        logger.info("Task DONE — interview=%s elapsed=%.2fs", interview_id, elapsed)

        # Chain: dispatch embedding generation
        from apps.embeddings.tasks import generate_embeddings_task
        generate_embeddings_task.delay(interview_id)
        logger.info("Embedding task dispatched for interview %s", interview_id)

        return {"status": "success", "interview_id": interview_id, "elapsed_seconds": round(elapsed, 2)}
    else:
        logger.error("Task returned failure — interview=%s elapsed=%.2fs", interview_id, elapsed)
        # Mark as failed before retrying so the state machine allows re-entry
        update_processing_status(interview, ProcessingStatus.FAILED, error="Transcription pipeline returned failure.")
        raise self.retry(exc=Exception("transcribe_interview returned False"))
