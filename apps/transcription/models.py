"""
InsightScribe - TranscriptChunk Model
Optimized for thousands of chunks per interview.
"""

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from apps.common.models import BaseModel


class TranscriptChunk(BaseModel):
    """A segment of transcribed audio with timestamps and speaker info."""

    interview = models.ForeignKey(
        "interviews.Interview",
        on_delete=models.CASCADE,
        related_name="transcript_chunks",
        db_index=True,
    )
    text = models.TextField()
    start_time = models.FloatField(help_text="Start time in seconds")
    end_time = models.FloatField(help_text="End time in seconds")
    chunk_index = models.PositiveIntegerField(default=0, help_text="Ordering index within interview")
    speaker_label = models.CharField(max_length=50, blank=True, default="", db_index=True)
    sentiment_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Sentiment score -1.0 to 1.0",
    )
    token_count = models.PositiveIntegerField(default=0)

    # Full-text search support (auto-populated via trigger or signal)
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        db_table = "transcript_chunks"
        ordering = ["interview", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["interview", "chunk_index"],
                name="uq_chunk_interview_index",
            ),
            models.CheckConstraint(
                check=models.Q(start_time__gte=0),
                name="ck_chunk_start_time_positive",
            ),
            models.CheckConstraint(
                check=models.Q(end_time__gte=models.F("start_time")),
                name="ck_chunk_end_after_start",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(sentiment_score__isnull=True)
                    | (models.Q(sentiment_score__gte=-1.0) & models.Q(sentiment_score__lte=1.0))
                ),
                name="ck_chunk_sentiment_range",
            ),
        ]
        indexes = [
            models.Index(fields=["interview", "chunk_index"], name="idx_chunk_interview_order"),
            models.Index(fields=["interview", "start_time"], name="idx_chunk_interview_time"),
            models.Index(fields=["interview", "is_deleted"], name="idx_chunk_interview_active"),
            GinIndex(fields=["search_vector"], name="idx_chunk_search_vector"),
            # Partial index for chunks with sentiment data (analytics queries)
            models.Index(
                fields=["interview", "sentiment_score"],
                name="idx_chunk_sentiment",
                condition=models.Q(sentiment_score__isnull=False),
            ),
        ]

    def __str__(self):
        return f"Chunk {self.chunk_index} ({self.start_time:.1f}s-{self.end_time:.1f}s)"

    @property
    def duration(self):
        """Duration of this chunk in seconds."""
        return self.end_time - self.start_time
