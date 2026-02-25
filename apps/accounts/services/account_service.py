"""
InsightScribe - Account Services
Business logic for user management and authentication.
"""

import logging

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger("apps.accounts")

User = get_user_model()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def register_user(email: str, password: str, full_name: str = "") -> tuple:
    """
    Create a new user account and return the user + token pair.
    Returns (user, tokens_dict).
    """
    user = User.objects.create_user(email=email, password=password, full_name=full_name)
    tokens = _generate_tokens_for_user(user)
    logger.info("User registered: %s", user.email)
    return user, tokens


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def authenticate_user(email: str, password: str) -> tuple:
    """
    Validate credentials and return (user, tokens_dict) or (None, error_msg).
    Uses constant-time comparison even when user is missing to prevent timing attacks.
    """
    try:
        user = User.objects.get(email=email.lower().strip())
    except User.DoesNotExist:
        # Run the hasher anyway to prevent timing-based user enumeration
        User().set_password(password)
        return None, "Invalid email or password."

    if not user.is_active:
        return None, "Invalid email or password."

    if not user.check_password(password):
        return None, "Invalid email or password."

    tokens = _generate_tokens_for_user(user)
    logger.info("User logged in: %s", user.email)
    return user, tokens


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------
def refresh_access_token(refresh_token_str: str) -> tuple:
    """
    Validate a refresh token and return new token pair.
    Returns (tokens_dict, None) on success, (None, error_msg) on failure.
    """
    try:
        refresh = RefreshToken(refresh_token_str)
        tokens = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
        return tokens, None
    except TokenError:
        return None, "Token is invalid or expired."


def blacklist_refresh_token(refresh_token_str: str) -> tuple:
    """
    Blacklist a refresh token (logout).
    Returns (True, None) on success, (False, error_msg) on failure.
    """
    try:
        token = RefreshToken(refresh_token_str)
        token.blacklist()
        return True, None
    except TokenError:
        return False, "Token is invalid or expired."


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
def get_user_by_id(user_id):
    """Retrieve user by UUID."""
    try:
        return User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        return None


def change_user_password(user, old_password: str, new_password: str) -> tuple:
    """Change password after verifying old password."""
    if not user.check_password(old_password):
        return False, "Current password is incorrect."
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    logger.info("Password changed for user: %s", user.email)
    return True, None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _generate_tokens_for_user(user) -> dict:
    """Issue a JWT access + refresh token pair for the given user."""
    from apps.accounts.serializers import CustomTokenObtainPairSerializer

    refresh = CustomTokenObtainPairSerializer.get_token(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }
