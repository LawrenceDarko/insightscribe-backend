"""
InsightScribe - Insight Report Models
"""

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class ReportType(models.TextChoices):
    FEATURE_REQUESTS = "feature_requests", "Top Feature Requests"
    FRUSTRATIONS = "frustrations", "Most Common Frustrations"
    POSITIVE_THEMES = "positive_themes", "Positive Themes"
    NEGATIVE_THEMES = "negative_themes", "Negative Themes"
    ONBOARDING = "onboarding", "Onboarding Issues"
    FULL = "full", "Full Report"


class ReportStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class InsightReport(BaseModel):
    """A generated insight report for a project."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="insight_reports",
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="insight_reports",
    )
    report_type = models.CharField(max_length=30, choices=ReportType.choices)
    status = models.CharField(
        max_length=20,
        choices=ReportStatus.choices,
        default=ReportStatus.PENDING,
        db_index=True,
    )
    title = models.CharField(max_length=255)
    content = models.JSONField(default=dict, help_text="Structured report JSON")
    metadata = models.JSONField(default=dict, blank=True, help_text="Report generation metadata")
    processing_error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "insight_reports"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["project", "report_type", "-created_at"],
                name="idx_report_project_type",
            ),
            models.Index(
                fields=["project", "status"],
                name="idx_report_project_status",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(status__in=[s.value for s in ReportStatus]),
                name="ck_report_valid_status",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.report_type}) [{self.status}]"
