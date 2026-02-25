"""
InsightScribe - Project Views (Function-Based)
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.common.responses import created_response, error_response, not_found_response, success_response

from .serializers import ProjectCreateSerializer, ProjectSerializer
from .services.project_service import (
    create_project,
    delete_project,
    get_project_for_user,
    get_user_projects,
    update_project,
)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def project_list_create_view(request):
    """List all projects or create a new one."""
    if request.method == "GET":
        projects = get_user_projects(request.user)
        serializer = ProjectSerializer(projects, many=True)
        return success_response(data=serializer.data)

    # POST
    serializer = ProjectCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(message="Validation failed.", code="VALIDATION_ERROR", details=serializer.errors)

    project = create_project(user=request.user, **serializer.validated_data)
    return created_response(data=ProjectSerializer(project).data, message="Project created.")


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def project_detail_view(request, project_id):
    """Retrieve, update, or soft-delete a project."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    if request.method == "GET":
        return success_response(data=ProjectSerializer(project).data)

    if request.method == "PATCH":
        serializer = ProjectCreateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed.", code="VALIDATION_ERROR", details=serializer.errors)
        project = update_project(project, **serializer.validated_data)
        return success_response(data=ProjectSerializer(project).data, message="Project updated.")

    # DELETE
    delete_project(project)
    return success_response(message="Project deleted.")
