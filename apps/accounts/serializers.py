"""
InsightScribe - Account Serializers
Production-ready serializers for JWT authentication.
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

# ---------------------------------------------------------------------------
# Reusable email normalizer
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _normalize_email(value: str) -> str:
    """Lowercase, strip, and regex-validate an email address."""
    email = value.lower().strip()
    if not EMAIL_RE.match(email):
        raise serializers.ValidationError("Enter a valid email address.")
    return email


# ---------------------------------------------------------------------------
# User (read-only)
# ---------------------------------------------------------------------------
class UserSerializer(serializers.ModelSerializer):
    """Read-only user representation."""

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "plan", "is_active", "created_at"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
class RegisterSerializer(serializers.Serializer):
    """User registration with strong password validation and anti-enumeration."""

    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(write_only=True, min_length=10, style={"input_type": "password"})
    password_confirm = serializers.CharField(write_only=True, min_length=10, style={"input_type": "password"})
    full_name = serializers.CharField(max_length=255, required=False, default="")

    def validate_email(self, value):
        email = _normalize_email(value)
        if User.objects.filter(email=email).exists():
            # Generic message to prevent user enumeration
            raise serializers.ValidationError("Unable to register with this email.")
        return email

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.get("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm", None)
        return User.objects.create_user(**validated_data)


# ---------------------------------------------------------------------------
# Login (custom token obtain pair)
# ---------------------------------------------------------------------------
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Extend JWT token to include custom claims (email, plan)."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["plan"] = user.plan
        return token

    def validate(self, attrs):
        # Normalize email before authentication
        email = attrs.get("email", "").lower().strip()
        attrs["email"] = email
        try:
            data = super().validate(attrs)
        except Exception:
            # Generic error to prevent user enumeration
            raise serializers.ValidationError(
                {"detail": "Invalid email or password."}
            )
        return data


class LoginSerializer(serializers.Serializer):
    """Lightweight input serializer for the FBV login view."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------
class TokenRefreshInputSerializer(serializers.Serializer):
    """Input serializer for the FBV token-refresh view."""

    refresh = serializers.CharField()


# ---------------------------------------------------------------------------
# Profile update
# ---------------------------------------------------------------------------
class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Allow users to update non-sensitive profile fields."""

    class Meta:
        model = User
        fields = ["full_name"]


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------
class ChangePasswordSerializer(serializers.Serializer):
    """Password change for authenticated users."""

    old_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, min_length=10, style={"input_type": "password"})
    new_password_confirm = serializers.CharField(write_only=True, min_length=10, style={"input_type": "password"})

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs.get("new_password_confirm"):
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
        return attrs
