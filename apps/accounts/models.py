"""
InsightScribe - Custom User Model
Email-based authentication with plan support.
"""

import uuid

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Custom manager for email-based User model."""

    def _create_user(self, email, password, **extra_fields):
        """Internal helper shared by create_user / create_superuser."""
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email).lower().strip()
        user = self.model(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)

    def active(self):
        """Return only active users."""
        return self.get_queryset().filter(is_active=True)


class PlanChoices(models.TextChoices):
    FREE = "free", "Free"
    PRO = "pro", "Pro"


class User(AbstractBaseUser, PermissionsMixin):
    """Custom User: email as username, UUID PK, plan support."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, max_length=255, db_index=True)
    full_name = models.CharField(max_length=255, blank=True, default="")
    plan = models.CharField(max_length=10, choices=PlanChoices.choices, default=PlanChoices.FREE)

    is_active = models.BooleanField(default=True, db_index=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        verbose_name = "user"
        verbose_name_plural = "users"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"], name="idx_user_email"),
            models.Index(fields=["plan"], name="idx_user_plan"),
            models.Index(fields=["is_active", "-created_at"], name="idx_user_active_created"),
            models.Index(fields=["plan", "is_active"], name="idx_user_plan_active"),
        ]

    def __str__(self):
        return self.email

    @property
    def is_pro(self):
        return self.plan == PlanChoices.PRO
