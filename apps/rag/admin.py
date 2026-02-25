from django.contrib import admin

from .models import ChatMessage, ChatSession


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "project", "user", "created_at", "is_deleted"]
    list_filter = ["created_at", "is_deleted"]
    search_fields = ["title", "project__name", "user__email"]
    raw_id_fields = ["project", "user"]
    list_select_related = ["project", "user"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "session", "role", "token_count", "created_at"]
    list_filter = ["role", "created_at"]
    search_fields = ["content"]
    raw_id_fields = ["session"]
    readonly_fields = ["id", "created_at"]
