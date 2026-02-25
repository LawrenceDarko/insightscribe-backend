"""
InsightScribe - Insight Views (Function-Based)
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.common.responses import (
    created_response,
    error_response,
    not_found_response,
    success_response,
)
from apps.projects.services.project_service import get_project_for_user

from .serializers import (
    GenerateReportSerializer,
    InsightReportListSerializer,
    InsightReportSerializer,
)
from .services.report_service import (
    delete_report,
    generate_report,
    get_project_reports,
    get_report_detail,
)

logger = logging.getLogger("apps.insights")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_report_view(request, project_id):
    """Generate a new insight report for a project."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    serializer = GenerateReportSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            message="Validation failed.",
            code="VALIDATION_ERROR",
            details=serializer.errors,
        )

    try:
        report, err = generate_report(
            project=project,
            user=request.user,
            report_type=serializer.validated_data["report_type"],
        )
    except RuntimeError as exc:
        logger.error("Report generation runtime error: %s", exc)
        return error_response(
            message="Embedding service unavailable.",
            code="SERVICE_UNAVAILABLE",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    if err:
        return error_response(message=err, code="REPORT_ERROR")

    return created_response(
        data=InsightReportSerializer(report).data,
        message="Report generated.",
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_list_view(request, project_id):
    """List insight reports for a project (light payload)."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    report_type = request.query_params.get("type")
    reports = get_project_reports(project, report_type=report_type)
    serializer = InsightReportListSerializer(reports, many=True)
    return success_response(data=serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_detail_view(request, project_id, report_id):
    """Retrieve a single insight report with full content."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    report = get_report_detail(report_id, project)
    if not report:
        return not_found_response("Report not found.")

    return success_response(data=InsightReportSerializer(report).data)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_report_view(request, project_id, report_id):
    """Soft-delete an insight report."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    deleted = delete_report(report_id, project)
    if not deleted:
        return not_found_response("Report not found.")

    return success_response(message="Report deleted.", status_code=status.HTTP_200_OK)
