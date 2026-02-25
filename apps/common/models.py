"""
InsightScribe - Abstract Base Models
Shared model mixins used across all apps.
"""

import uuid

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Abstract base with timezone-aware created/updated timestamps."""

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class UUIDModel(models.Model):
    """Abstract base with UUID primary key."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that supports soft-delete filtering and bulk operations."""

    def active(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)

    def soft_delete(self):
        """Bulk soft-delete."""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def restore(self):
        """Bulk restore."""
        return self.update(is_deleted=False, deleted_at=None)


class SoftDeleteManager(models.Manager):
    """Manager that filters out soft-deleted objects by default."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).active()


class AllObjectsManager(models.Manager):
    """Manager that includes soft-deleted objects."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    """Abstract base supporting soft delete with atomic operations."""

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def soft_delete(self):
        """Atomically mark the record as deleted without removing from DB."""
        now = timezone.now()
        type(self).all_objects.filter(pk=self.pk).update(
            is_deleted=True, deleted_at=now
        )
        self.is_deleted = True
        self.deleted_at = now

    def restore(self):
        """Atomically restore a soft-deleted record."""
        type(self).all_objects.filter(pk=self.pk).update(
            is_deleted=False, deleted_at=None
        )
        self.is_deleted = False
        self.deleted_at = None


class BaseModel(UUIDModel, TimeStampedModel, SoftDeleteModel):
    """
    Full base model combining UUID PK, timestamps, and soft delete.
    Inherit from this for all InsightScribe domain models.
    """

    class Meta:
        abstract = True
        ordering = ["-created_at"]
