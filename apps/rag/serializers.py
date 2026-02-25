"""
InsightScribe - RAG / Chat Serializers
"""

from rest_framework import serializers

from .models import ChatMessage, ChatSession


# ===========================================================================
# Shared component serializers (used by both RAG and Chat responses)
# ===========================================================================
class SupportingQuoteSerializer(serializers.Serializer):
    """A direct quote from a transcript chunk supporting the answer."""

    text = serializers.CharField()
    interview_title = serializers.CharField(allow_blank=True)
    start_time = serializers.FloatField(allow_null=True)
    end_time = serializers.FloatField(allow_null=True)
    speaker = serializers.CharField(allow_blank=True)


class RAGSourceSerializer(serializers.Serializer):
    """A transcript chunk returned from the similarity search."""

    chunk_id = serializers.CharField()
    interview_id = serializers.CharField()
    interview_title = serializers.CharField()
    text = serializers.CharField()
    start_time = serializers.FloatField(allow_null=True)
    end_time = serializers.FloatField(allow_null=True)
    chunk_index = serializers.IntegerField()
    speaker = serializers.CharField(allow_blank=True)
    similarity = serializers.FloatField()


# ===========================================================================
# RAG (one-shot) serializers
# ===========================================================================
class RAGQuerySerializer(serializers.Serializer):
    question = serializers.CharField(
        max_length=2000,
        help_text="Natural-language question to answer using project interviews.",
    )


class RAGResponseSerializer(serializers.Serializer):
    """Structured response from the one-shot RAG query engine."""

    answer = serializers.CharField()
    supporting_quotes = SupportingQuoteSerializer(many=True)
    sources = RAGSourceSerializer(many=True)
    question = serializers.CharField()
    result_count = serializers.IntegerField()
    elapsed_seconds = serializers.FloatField()


# ===========================================================================
# Chat serializers
# ===========================================================================
class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = [
            "id",
            "role",
            "content",
            "sources",
            "supporting_quotes",
            "token_count",
            "created_at",
        ]
        read_only_fields = fields


class ChatSessionSerializer(serializers.Serializer):
    """Lightweight session listing — uses annotated ``message_count``."""

    id = serializers.UUIDField()
    project_id = serializers.UUIDField()
    title = serializers.CharField()
    message_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class ChatQuerySerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000)
    session_id = serializers.UUIDField(required=False, allow_null=True)


class RenameSessionSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, min_length=1)


class ChatResponseSerializer(serializers.Serializer):
    """Structured response from the conversational chat endpoint."""

    session_id = serializers.CharField()
    message_id = serializers.IntegerField()
    answer = serializers.CharField()
    supporting_quotes = SupportingQuoteSerializer(many=True)
    sources = RAGSourceSerializer(many=True)
    question = serializers.CharField()
    elapsed_seconds = serializers.FloatField(allow_null=True)
