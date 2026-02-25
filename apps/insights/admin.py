from django.contrib import admin

from .models import InsightReport


@admin.register(InsightReport)
class InsightReportAdmin(admin.ModelAdmin):
    list_display = ["title", "project", "report_type", "status", "user", "created_at", "is_deleted"]
    list_filter = ["report_type", "status", "created_at", "is_deleted"]
    search_fields = ["title", "project__name", "user__email"]
    raw_id_fields = ["project", "user"]
    list_select_related = ["project", "user"]
    readonly_fields = ["id", "content", "metadata", "created_at", "updated_at"]
