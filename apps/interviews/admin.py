from django.contrib import admin

from .models import Interview


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ["title", "project", "processing_status", "file_size", "file_hash_short", "created_at"]
    list_filter = ["processing_status", "created_at"]
    search_fields = ["title", "file_name", "file_hash", "project__name"]
    readonly_fields = ["id", "file_hash", "created_at", "updated_at"]

    @admin.display(description="Hash")
    def file_hash_short(self, obj):
        return obj.file_hash[:12] + "…" if obj.file_hash else "—"
