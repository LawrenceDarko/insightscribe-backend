"""
InsightScribe - TranscriptChunk Serializers
"""

from rest_framework import serializers

from .models import TranscriptChunk


class TranscriptChunkSerializer(serializers.ModelSerializer):
    """Read-only representation of a transcript chunk."""

    duration = serializers.FloatField(read_only=True)

    class Meta:
        model = TranscriptChunk
        fields = [
            "id", "interview_id", "text", "start_time", "end_time",
            "chunk_index", "speaker_label", "sentiment_score", "token_count",
            "duration", "created_at",
        ]
        read_only_fields = fields


class TranscriptSearchSerializer(serializers.Serializer):
    """Query params for chunk search / filtering."""

    speaker = serializers.CharField(required=False, max_length=50)
    search = serializers.CharField(required=False, max_length=500)
