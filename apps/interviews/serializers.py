"""
InsightScribe - Interview Serializers
"""

import os

from django.conf import settings
from rest_framework import serializers

from .models import Interview


class InterviewSerializer(serializers.ModelSerializer):
    """Read-only interview representation."""

    is_processing = serializers.BooleanField(read_only=True)
    is_complete = serializers.BooleanField(read_only=True)
    is_failed = serializers.BooleanField(read_only=True)

    class Meta:
        model = Interview
        fields = [
            "id", "project_id", "title", "file_url", "file_name", "file_size",
            "file_hash", "duration_seconds",
            "processing_status", "processing_progress", "processing_error",
            "processing_started_at", "processing_completed_at",
            "is_processing", "is_complete", "is_failed",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class InterviewUploadSerializer(serializers.Serializer):
    """Validate the multipart upload payload before hitting the service layer."""

    title = serializers.CharField(max_length=255, required=False, default="")
    file = serializers.FileField()

    def validate_file(self, file):
        """Quick client-facing checks (detailed validation is in the service layer)."""
        if file.size == 0:
            raise serializers.ValidationError("Uploaded file is empty.")

        max_bytes = getattr(settings, "MAX_UPLOAD_SIZE_BYTES", 200 * 1024 * 1024)
        max_mb = getattr(settings, "MAX_UPLOAD_SIZE_MB", 200)
        if file.size > max_bytes:
            raise serializers.ValidationError(
                f"File size ({file.size / (1024 * 1024):.1f}MB) exceeds the {max_mb}MB limit."
            )

        _, ext = os.path.splitext(file.name)
        allowed = getattr(settings, "ALLOWED_AUDIO_EXTENSIONS", [".mp3", ".wav", ".mp4"])
        if ext.lower() not in allowed:
            raise serializers.ValidationError(
                f"Invalid file extension '{ext}'. Allowed: {', '.join(allowed)}."
            )

        return file


class InterviewListQuerySerializer(serializers.Serializer):
    """Query params for the interview list endpoint."""

    status = serializers.ChoiceField(
        choices=["uploaded", "transcribing", "embedding", "complete", "failed"],
        required=False,
    )
    ordering = serializers.ChoiceField(
        choices=["created_at", "-created_at", "file_size", "-file_size", "title", "-title"],
        required=False,
        default="-created_at",
    )
