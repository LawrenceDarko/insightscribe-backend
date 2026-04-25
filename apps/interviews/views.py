"""
InsightScribe - Interview Views (Function-Based)
Authenticated endpoints for uploading, listing, retrieving, and managing interviews.
"""

import logging

from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.common.responses import created_response, error_response, not_found_response, success_response
from apps.projects.services.project_service import get_project_for_user

from .serializers import InterviewListQuerySerializer, InterviewSerializer, InterviewUploadSerializer
from .services.upload_service import (
    create_interview_from_link,
    create_interview_from_transcript,
    get_interview,
    get_project_interviews,
    mark_for_reprocessing,
    upload_interview,
)

logger = logging.getLogger("apps.interviews")


# ---------------------------------------------------------------------------
# GET  /api/v1/projects/<project_id>/interviews/
# POST /api/v1/projects/<project_id>/interviews/
# ---------------------------------------------------------------------------
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def interview_list_create_view(request, project_id):
    """List interviews or upload a new one for a project."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    if request.method == "GET":
        return _list_interviews(request, project)

    return _upload_interview(request, project)


def _list_interviews(request, project):
    """Handle GET: list interviews with optional filtering."""
    query_ser = InterviewListQuerySerializer(data=request.query_params)
    query_ser.is_valid(raise_exception=True)

    interviews = get_project_interviews(project)

    # Filter by status if provided
    status_filter = query_ser.validated_data.get("status")
    if status_filter:
        interviews = interviews.filter(processing_status=status_filter)

    # Ordering
    ordering = query_ser.validated_data.get("ordering", "-created_at")
    interviews = interviews.order_by(ordering)

    serializer = InterviewSerializer(interviews, many=True)
    return success_response(
        data={
            "count": interviews.count(),
            "interviews": serializer.data,
        }
    )


def _upload_interview(request, project):
    """Handle POST: validate and upload a new interview from file, text, or link."""
    serializer = InterviewUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            message="Validation failed.",
            code="VALIDATION_ERROR",
            details=serializer.errors,
        )

    data = serializer.validated_data
    title = data.get("title", "")

    if data.get("file"):
        interview, err = upload_interview(
            project=project,
            file=data["file"],
            title=title,
        )
    elif data.get("transcript_text"):
        interview, err = create_interview_from_transcript(
            project=project,
            transcript_text=data["transcript_text"],
            title=title,
        )
    else:
        interview, err = create_interview_from_link(
            project=project,
            media_url=data["media_url"],
            title=title,
        )

    if err:
        return error_response(message=err, code="UPLOAD_ERROR")

    logger.info(
        "Interview %s uploaded by user %s to project %s",
        interview.id, request.user.id, project.id,
    )

    return created_response(
        data=InterviewSerializer(interview).data,
        message="Interview uploaded successfully. Processing will begin shortly.",
    )


# ---------------------------------------------------------------------------
# GET    /api/v1/projects/<project_id>/interviews/<interview_id>/
# DELETE /api/v1/projects/<project_id>/interviews/<interview_id>/
# ---------------------------------------------------------------------------
@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated])
def interview_detail_view(request, project_id, interview_id):
    """Retrieve or soft-delete an interview."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    interview = get_interview(interview_id, project)
    if not interview:
        return not_found_response("Interview not found.")

    if request.method == "GET":
        return success_response(data=InterviewSerializer(interview).data)

    # DELETE — soft delete
    interview.soft_delete()
    logger.info("Interview %s soft-deleted by user %s", interview.id, request.user.id)
    return success_response(message="Interview deleted.")


# ---------------------------------------------------------------------------
# POST /api/v1/projects/<project_id>/interviews/<interview_id>/reprocess/
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def interview_reprocess_view(request, project_id, interview_id):
    """Re-queue a failed interview for processing."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    interview = get_interview(interview_id, project)
    if not interview:
        return not_found_response("Interview not found.")

    ok, err = mark_for_reprocessing(interview)
    if not ok:
        return error_response(message=err, code="REPROCESS_ERROR")

    logger.info("Interview %s queued for reprocessing by user %s", interview.id, request.user.id)
    return success_response(
        data=InterviewSerializer(interview).data,
        message="Interview queued for reprocessing.",
    )
