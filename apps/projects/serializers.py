"""
InsightScribe - Project Serializers
"""

from rest_framework import serializers

from .models import Project


class ProjectSerializer(serializers.ModelSerializer):
    interview_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ["id", "name", "description", "interview_count", "created_at", "updated_at"]
        read_only_fields = ["id", "interview_count", "created_at", "updated_at"]

    def get_interview_count(self, obj):
        return obj.interviews.filter(is_deleted=False).count() if hasattr(obj, "interviews") else 0


class ProjectCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, default="", allow_blank=True)
