"""
InsightScribe - Insight Serializers
"""

from rest_framework import serializers

from .models import InsightReport, ReportType


# ---------------------------------------------------------------------------
# Nested / shared
# ---------------------------------------------------------------------------

class SupportingQuoteSerializer(serializers.Serializer):
    text = serializers.CharField()
    interview_title = serializers.CharField()
    start_time = serializers.FloatField(allow_null=True)
    end_time = serializers.FloatField(allow_null=True)
    speaker = serializers.CharField(allow_blank=True, default="")


class ThemeSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    theme = serializers.CharField()
    description = serializers.CharField()
    frequency = serializers.IntegerField()
    sentiment_avg = serializers.FloatField()
    supporting_quotes = SupportingQuoteSerializer(many=True)


class ReportContentSerializer(serializers.Serializer):
    """Validates the structured ``content`` JSON of a completed report."""
    themes = ThemeSerializer(many=True)
    summary = serializers.CharField(allow_blank=True, default="")
    total_chunks_analyzed = serializers.IntegerField(default=0)
    methodology = serializers.CharField(allow_blank=True, default="")


class SentimentDistributionSerializer(serializers.Serializer):
    average_sentiment = serializers.FloatField()
    total_scored_chunks = serializers.IntegerField()
    positive_ratio = serializers.FloatField()
    neutral_ratio = serializers.FloatField()
    negative_ratio = serializers.FloatField()


class ReportMetadataSerializer(serializers.Serializer):
    chunks_analyzed = serializers.IntegerField()
    total_project_chunks = serializers.IntegerField()
    interviews_included = serializers.IntegerField()
    generation_time_seconds = serializers.FloatField()
    sentiment_distribution = SentimentDistributionSerializer(required=False)


# ---------------------------------------------------------------------------
# Request serializers
# ---------------------------------------------------------------------------

class GenerateReportSerializer(serializers.Serializer):
    report_type = serializers.ChoiceField(choices=ReportType.choices)


# ---------------------------------------------------------------------------
# Response serializers
# ---------------------------------------------------------------------------

class InsightReportSerializer(serializers.ModelSerializer):
    content = ReportContentSerializer(read_only=True)
    metadata = ReportMetadataSerializer(read_only=True)

    class Meta:
        model = InsightReport
        fields = [
            "id",
            "project_id",
            "report_type",
            "status",
            "title",
            "content",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields


class InsightReportListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views — omits full content."""
    theme_count = serializers.SerializerMethodField()
    chunks_analyzed = serializers.SerializerMethodField()

    class Meta:
        model = InsightReport
        fields = [
            "id",
            "report_type",
            "status",
            "title",
            "theme_count",
            "chunks_analyzed",
            "created_at",
        ]
        read_only_fields = fields

    def get_theme_count(self, obj) -> int:
        content = obj.content or {}
        themes = content.get("themes", [])
        return len(themes) if isinstance(themes, list) else 0

    def get_chunks_analyzed(self, obj) -> int:
        metadata = obj.metadata or {}
        return metadata.get("chunks_analyzed", 0)
