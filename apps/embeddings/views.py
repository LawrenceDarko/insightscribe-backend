"""
InsightScribe - Embedding Views (Function-Based)
Endpoints for triggering embedding generation, similarity search, and stats.
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.common.responses import error_response, not_found_response, success_response
from apps.interviews.models import ProcessingStatus
from apps.interviews.services.upload_service import get_interview
from apps.projects.services.project_service import get_project_for_user

from .serializers import EmbeddingStatsSerializer, SearchQuerySerializer, SimilarityResultSerializer
from .services.embedding_service import generate_query_embedding, get_embedding_stats, similarity_search
from .tasks import generate_embeddings_task

logger = logging.getLogger("apps.embeddings")


# ---------------------------------------------------------------------------
# POST  .../embeddings/generate/
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def trigger_embedding_view(request, project_id, interview_id):
    """Trigger async embedding generation for a transcribed interview."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    interview = get_interview(interview_id, project)
    if not interview:
        return not_found_response("Interview not found.")

    # Only allow embedding from valid FSM states
    allowed_states = (ProcessingStatus.EMBEDDING, ProcessingStatus.FAILED)
    if interview.processing_status not in allowed_states:
        return error_response(
            message=f"Interview must be in 'embedding' or 'failed' state to generate embeddings. "
                    f"Current state: '{interview.processing_status}'.",
            code="INVALID_STATE",
            status_code=status.HTTP_409_CONFLICT,
        )

    task = generate_embeddings_task.delay(str(interview.id))

    return success_response(
        message="Embedding generation started.",
        data={
            "interview_id": str(interview.id),
            "task_id": task.id,
        },
        status_code=status.HTTP_202_ACCEPTED,
    )


# ---------------------------------------------------------------------------
# POST  .../embeddings/search/
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def similarity_search_view(request, project_id):
    """
    Semantic search across all embedded transcript chunks in a project.
    """
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    serializer = SearchQuerySerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            message="Invalid search query.",
            code="VALIDATION_ERROR",
            details=serializer.errors,
        )

    query = serializer.validated_data["query"]
    top_k = serializer.validated_data.get("top_k", 10)
    score_threshold = serializer.validated_data.get("score_threshold")

    try:
        query_vector = generate_query_embedding(query)
    except Exception as exc:
        logger.error("Query embedding failed: %s", exc)
        return error_response(
            message="Failed to generate query embedding.",
            code="EMBEDDING_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    results = similarity_search(
        query_vector=query_vector,
        project_id=project.id,
        top_k=top_k,
        score_threshold=score_threshold,
    )

    result_serializer = SimilarityResultSerializer(results, many=True)
    return success_response(
        data={
            "query": query,
            "result_count": len(results),
            "results": result_serializer.data,
        },
    )


# ---------------------------------------------------------------------------
# GET  .../embeddings/stats/
# ---------------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def embedding_stats_view(request, project_id, interview_id):
    """Return embedding coverage statistics for a given interview."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    interview = get_interview(interview_id, project)
    if not interview:
        return not_found_response("Interview not found.")

    stats = get_embedding_stats(interview)
    serializer = EmbeddingStatsSerializer(stats)
    return success_response(data=serializer.data)
