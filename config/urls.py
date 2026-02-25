"""
InsightScribe - Root URL Configuration
All API endpoints versioned under /api/v1/
"""

from django.contrib import admin
from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.embeddings.urls import project_urlpatterns as embedding_project_urls


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint for Railway / load balancers."""
    return Response({"status": "healthy", "service": "InsightScribe API"})


urlpatterns = [
    # Health check
    path("health/", health_check, name="health-check"),

    # Admin
    path("admin/", admin.site.urls),

    # API v1
    path("api/v1/auth/", include("apps.accounts.urls", namespace="accounts")),
    path("api/v1/projects/", include("apps.projects.urls", namespace="projects")),
    path(
        "api/v1/projects/<uuid:project_id>/interviews/",
        include("apps.interviews.urls", namespace="interviews"),
    ),
    path(
        "api/v1/projects/<uuid:project_id>/interviews/<uuid:interview_id>/",
        include("apps.transcription.urls", namespace="transcription"),
    ),
    path(
        "api/v1/projects/<uuid:project_id>/interviews/<uuid:interview_id>/embeddings/",
        include("apps.embeddings.urls", namespace="embeddings"),
    ),
    path(
        "api/v1/projects/<uuid:project_id>/embeddings/",
        include(
            (embedding_project_urls, "embeddings-project"),
        ),
    ),
    path(
        "api/v1/projects/<uuid:project_id>/",
        include("apps.rag.urls", namespace="rag"),
    ),
    path(
        "api/v1/projects/<uuid:project_id>/insights/",
        include("apps.insights.urls", namespace="insights"),
    ),
]
