"""
InsightScribe - Embedding Serializers
"""

from rest_framework import serializers

from .models import Embedding


class EmbeddingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Embedding
        fields = ["id", "transcript_chunk_id", "interview_id", "model_name", "created_at"]
        read_only_fields = fields


class SearchQuerySerializer(serializers.Serializer):
    """Validate incoming similarity-search requests."""

    query = serializers.CharField(
        max_length=2000,
        help_text="Natural-language question to search against transcript chunks.",
    )
    top_k = serializers.IntegerField(
        required=False,
        default=10,
        min_value=1,
        max_value=50,
        help_text="Maximum number of results to return (1–50).",
    )
    score_threshold = serializers.FloatField(
        required=False,
        default=None,
        min_value=0.0,
        max_value=1.0,
        help_text="Minimum similarity score (0–1). Results below this are excluded.",
    )


class SimilarityResultSerializer(serializers.Serializer):
    """Serialize a single similarity-search result."""

    chunk_id = serializers.CharField()
    interview_id = serializers.CharField()
    interview_title = serializers.CharField()
    text = serializers.CharField()
    start_time = serializers.FloatField(allow_null=True)
    end_time = serializers.FloatField(allow_null=True)
    chunk_index = serializers.IntegerField()
    speaker_label = serializers.CharField(allow_blank=True)
    token_count = serializers.IntegerField()
    similarity = serializers.FloatField()


class EmbeddingStatsSerializer(serializers.Serializer):
    """Serialize embedding coverage stats for an interview."""

    interview_id = serializers.CharField()
    total_chunks = serializers.IntegerField()
    embedded_chunks = serializers.IntegerField()
    coverage_pct = serializers.FloatField()
    model_name = serializers.CharField()
    dimensions = serializers.IntegerField()
