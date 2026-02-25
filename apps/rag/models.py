"""
InsightScribe - RAG / Chat Models
Stores conversation history for project-level chat.
"""

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class ChatSession(BaseModel):
    """A chat session within a project."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="chat_sessions",
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )
    title = models.CharField(max_length=255, blank=True, default="New Chat")

    class Meta:
        db_table = "chat_sessions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "user", "-created_at"], name="idx_chat_project_user"),
        ]

    def __str__(self):
        return f"Chat: {self.title} (Project: {self.project.name})"


class ChatMessage(models.Model):
    """Individual message in a chat session."""

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
        db_index=True,
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    sources = models.JSONField(
        default=list,
        blank=True,
        help_text="Raw similarity-search results (chunk references)",
    )
    supporting_quotes = models.JSONField(
        default=list,
        blank=True,
        help_text="LLM-extracted supporting quotes with timestamps",
    )
    token_count = models.PositiveIntegerField(
        default=0,
        help_text="Approximate token count of this message (for context-window budgeting)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_messages"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"], name="idx_chatmsg_session_time"),
            models.Index(fields=["session", "role"], name="idx_chatmsg_session_role"),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:60]}"
