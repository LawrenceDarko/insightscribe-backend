from django.contrib import admin

from .models import TranscriptChunk


@admin.register(TranscriptChunk)
class TranscriptChunkAdmin(admin.ModelAdmin):
    list_display = ["interview", "chunk_index", "start_time", "end_time", "speaker_label", "token_count"]
    list_filter = ["interview__processing_status"]
    search_fields = ["text", "interview__title"]
    readonly_fields = ["id", "created_at", "updated_at"]
