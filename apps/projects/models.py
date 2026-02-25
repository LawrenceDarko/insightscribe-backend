"""
InsightScribe - Project Model
"""

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Project(BaseModel):
    """A research project owned by a user, containing interviews."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
        db_index=True,
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "projects"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                condition=models.Q(is_deleted=False),
                name="uq_project_user_name_active",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_project_user_created"),
            models.Index(fields=["user", "is_deleted"], name="idx_project_user_active"),
            models.Index(fields=["name"], name="idx_project_name"),
        ]

    def __str__(self):
        return f"{self.name} ({self.user.email})"

    @property
    def interview_count(self):
        """Active interview count (cached via annotation when available)."""
        if hasattr(self, "_interview_count"):
            return self._interview_count
        return self.interviews.filter(is_deleted=False).count()
