"""
InsightScribe - Interview URLs
"""

from django.urls import path

from . import views

app_name = "interviews"

urlpatterns = [
    path("", views.interview_list_create_view, name="interview-list-create"),
    path("<uuid:interview_id>/", views.interview_detail_view, name="interview-detail"),
    path("<uuid:interview_id>/reprocess/", views.interview_reprocess_view, name="interview-reprocess"),
]
