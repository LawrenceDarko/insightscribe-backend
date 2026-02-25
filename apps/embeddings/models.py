"""
InsightScribe - Embedding Model (pgvector)
Stores vector representations of transcript chunks for similarity search.
"""

import uuid

from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField


class Embedding(models.Model):
    """Vector embedding for a transcript chunk, stored via pgvector."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transcript_chunk = models.OneToOneField(
        "transcription.TranscriptChunk",
        on_delete=models.CASCADE,
        related_name="embedding",
        db_index=True,
    )
    # Denormalized FK for efficient project-scoped similarity queries
    # Avoids JOIN through transcript_chunk -> interview -> project
    interview = models.ForeignKey(
        "interviews.Interview",
        on_delete=models.CASCADE,
        related_name="embeddings",
        db_index=True,
    )
    vector = VectorField(
        dimensions=getattr(settings, "OPENAI_EMBEDDING_DIMENSIONS", 1536),
    )
    model_name = models.CharField(
        max_length=50,
        default="text-embedding-3-small",
        help_text="Embedding model used to generate this vector",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "embeddings"
        indexes = [
            HnswIndex(
                name="idx_embedding_vector_cosine",
                fields=["vector"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            # For project-scoped similarity queries via interview FK
            models.Index(
                fields=["interview"],
                name="idx_embedding_interview",
            ),
        ]

    def __str__(self):
        return f"Embedding for chunk {self.transcript_chunk_id}"

    def save(self, *args, **kwargs):
        """Auto-populate denormalized interview FK from transcript_chunk."""
        if not self.interview_id and self.transcript_chunk_id:
            self.interview_id = self.transcript_chunk.interview_id
        super().save(*args, **kwargs)
