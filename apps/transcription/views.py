"""
InsightScribe - Transcription Views (Function-Based)
Endpoints for triggering transcription and querying transcript chunks.
"""

import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.common.responses import error_response, not_found_response, success_response
from apps.interviews.models import ProcessingStatus
from apps.interviews.services.upload_service import get_interview
from apps.projects.services.project_service import get_project_for_user

from .models import TranscriptChunk
from .serializers import TranscriptChunkSerializer, TranscriptSearchSerializer
from .tasks import transcribe_interview_task

logger = logging.getLogger("apps.transcription")

# States from which transcription can be triggered
_TRIGGERABLE_STATES = {ProcessingStatus.UPLOADED, ProcessingStatus.FAILED}


# ---------------------------------------------------------------------------
# POST /api/v1/projects/<pid>/interviews/<iid>/transcribe/
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def trigger_transcription_view(request, project_id, interview_id):
    """
    Trigger async transcription for an uploaded interview.
    Dispatches a Celery task — does NOT block the request cycle.
    """
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    interview = get_interview(interview_id, project)
    if not interview:
        return not_found_response("Interview not found.")

    if interview.processing_status not in _TRIGGERABLE_STATES:
        return error_response(
            message=(
                f"Cannot transcribe: interview is in '{interview.get_processing_status_display()}' state. "
                f"Only interviews with status 'uploaded' or 'failed' can be transcribed."
            ),
            code="INVALID_STATE",
        )

    # Dispatch to Celery
    task = transcribe_interview_task.delay(str(interview.id))

    logger.info(
        "Transcription queued: interview=%s task_id=%s by user=%s",
        interview.id, task.id, request.user.id,
    )

    return success_response(
        message="Transcription queued for background processing.",
        data={
            "interview_id": str(interview.id),
            "task_id": task.id,
            "current_status": interview.processing_status,
        },
    )


# ---------------------------------------------------------------------------
# GET /api/v1/projects/<pid>/interviews/<iid>/chunks/
# ---------------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def transcript_chunks_view(request, project_id, interview_id):
    """
    List all transcript chunks for an interview.
    Supports optional query params:
      - speaker: filter by speaker_label
      - search: full-text search across chunk text
    """
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    interview = get_interview(interview_id, project)
    if not interview:
        return not_found_response("Interview not found.")

    chunks = TranscriptChunk.objects.filter(
        interview=interview,
        is_deleted=False,
    ).order_by("chunk_index")

    # Optional filters
    speaker = request.query_params.get("speaker")
    if speaker:
        chunks = chunks.filter(speaker_label__iexact=speaker)

    search_query = request.query_params.get("search")
    if search_query:
        chunks = chunks.filter(text__icontains=search_query)

    serializer = TranscriptChunkSerializer(chunks, many=True)
    return success_response(
        data={
            "interview_id": str(interview.id),
            "processing_status": interview.processing_status,
            "count": chunks.count(),
            "chunks": serializer.data,
        }
    )


# ---------------------------------------------------------------------------
# GET /api/v1/projects/<pid>/interviews/<iid>/transcript/
# ---------------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def full_transcript_view(request, project_id, interview_id):
    """
    Return the full reconstructed transcript as a single text block,
    along with summary metadata.
    """
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    interview = get_interview(interview_id, project)
    if not interview:
        return not_found_response("Interview not found.")

    chunks = (
        TranscriptChunk.objects
        .filter(interview=interview, is_deleted=False)
        .order_by("chunk_index")
        .values_list("text", flat=True)
    )
    full_text = "\n\n".join(chunks)
    chunk_count = len(chunks)

    return success_response(
        data={
            "interview_id": str(interview.id),
            "processing_status": interview.processing_status,
            "duration_seconds": interview.duration_seconds,
            "chunk_count": chunk_count,
            "transcript": full_text,
        }
    )
