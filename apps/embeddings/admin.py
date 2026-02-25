from django.contrib import admin

from .models import Embedding


@admin.register(Embedding)
class EmbeddingAdmin(admin.ModelAdmin):
    list_display = ["id", "transcript_chunk", "interview", "model_name", "created_at"]
    list_filter = ["model_name", "created_at"]
    search_fields = ["transcript_chunk__text"]
    readonly_fields = ["id", "vector", "created_at"]
    raw_id_fields = ["transcript_chunk", "interview"]
    list_select_related = ["transcript_chunk", "interview"]
