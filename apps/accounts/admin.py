from django.contrib import admin
from django.contrib.auth import get_user_model

User = get_user_model()


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["email", "full_name", "plan", "is_active", "created_at"]
    list_filter = ["plan", "is_active", "is_staff"]
    search_fields = ["email", "full_name"]
    ordering = ["-created_at"]
    readonly_fields = ["id", "created_at", "updated_at"]
