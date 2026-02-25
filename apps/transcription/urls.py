"""
InsightScribe - Transcription URLs
Nested under /api/v1/projects/<project_id>/interviews/<interview_id>/
"""

from django.urls import path

from . import views

app_name = "transcription"

urlpatterns = [
    path("transcribe/", views.trigger_transcription_view, name="trigger-transcription"),
    path("chunks/", views.transcript_chunks_view, name="transcript-chunks"),
    path("transcript/", views.full_transcript_view, name="full-transcript"),
]
