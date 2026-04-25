"""
InsightScribe - Interview Model
"""

from django.db import models

from apps.common.models import BaseModel


class ProcessingStatus(models.TextChoices):
    UPLOADED = "uploaded", "Uploaded"
    TRANSCRIBING = "transcribing", "Transcribing"
    EMBEDDING = "embedding", "Embedding"
    COMPLETE = "complete", "Complete"
    FAILED = "failed", "Failed"


class InterviewSourceType(models.TextChoices):
    FILE = "file", "File Upload"
    TRANSCRIPT = "transcript", "Manual Transcript"
    LINK = "link", "Media Link"


# Valid state transitions for processing pipeline
VALID_STATUS_TRANSITIONS = {
    ProcessingStatus.UPLOADED: [ProcessingStatus.TRANSCRIBING, ProcessingStatus.FAILED],
    ProcessingStatus.TRANSCRIBING: [ProcessingStatus.EMBEDDING, ProcessingStatus.FAILED],
    ProcessingStatus.EMBEDDING: [ProcessingStatus.COMPLETE, ProcessingStatus.FAILED],
    ProcessingStatus.COMPLETE: [],  # Terminal state
    ProcessingStatus.FAILED: [ProcessingStatus.TRANSCRIBING, ProcessingStatus.EMBEDDING],  # Retry
}


class Interview(BaseModel):
    """An uploaded audio interview linked to a project."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="interviews",
        db_index=True,
    )
    title = models.CharField(max_length=255, blank=True, default="")
    source_type = models.CharField(
        max_length=20,
        choices=InterviewSourceType.choices,
        default=InterviewSourceType.FILE,
        db_index=True,
    )
    file_url = models.URLField(max_length=2048, blank=True, default="")
    file_name = models.CharField(max_length=512, default="")
    file_size = models.BigIntegerField(
        default=0,
        help_text="File size in bytes",
    )
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="SHA-256 hash of the uploaded file for duplicate detection",
    )
    duration_seconds = models.FloatField(null=True, blank=True)
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.UPLOADED,
        db_index=True,
    )
    processing_progress = models.PositiveSmallIntegerField(
        default=0,
        help_text="Processing progress 0–100",
    )
    processing_error = models.TextField(blank=True, default="")
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "interviews"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(file_size__gte=0),
                name="ck_interview_file_size_positive",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(duration_seconds__isnull=True)
                    | models.Q(duration_seconds__gte=0)
                ),
                name="ck_interview_duration_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "-created_at"], name="idx_interview_project_created"),
            models.Index(fields=["project", "processing_status"], name="idx_interview_project_status"),
            models.Index(fields=["processing_status"], name="idx_interview_status"),
            models.Index(
                fields=["project", "is_deleted"],
                name="idx_interview_project_active",
            ),
        ]

    def __str__(self):
        return f"{self.title or self.file_name} ({self.processing_status})"

    def can_transition_to(self, new_status):
        """Check if the given status transition is valid."""
        allowed = VALID_STATUS_TRANSITIONS.get(self.processing_status, [])
        return new_status in allowed

    @property
    def is_processing(self):
        return self.processing_status in (
            ProcessingStatus.TRANSCRIBING,
            ProcessingStatus.EMBEDDING,
        )

    @property
    def is_complete(self):
        return self.processing_status == ProcessingStatus.COMPLETE

    @property
    def is_failed(self):
        return self.processing_status == ProcessingStatus.FAILED
