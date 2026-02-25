"""
InsightScribe - Project URLs
"""

from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list_create_view, name="project-list-create"),
    path("<uuid:project_id>/", views.project_detail_view, name="project-detail"),
]
