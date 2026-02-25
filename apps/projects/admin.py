from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "is_deleted", "created_at"]
    list_filter = ["is_deleted", "created_at"]
    search_fields = ["name", "user__email"]
    readonly_fields = ["id", "created_at", "updated_at"]
