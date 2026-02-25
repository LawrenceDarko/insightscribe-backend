"""
InsightScribe - Account Views (Function-Based)
Production-ready JWT authentication endpoints.
All views return standardized JSON envelopes via common.responses helpers.
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated

from apps.common.responses import created_response, error_response, success_response

from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    TokenRefreshInputSerializer,
    UserSerializer,
)
from .services.account_service import (
    authenticate_user,
    blacklist_refresh_token,
    change_user_password,
    refresh_access_token,
    register_user,
)
from .throttles import AuthBurstThrottle, AuthSustainedThrottle

logger = logging.getLogger("apps.accounts")


# ---------------------------------------------------------------------------
# POST /api/v1/auth/register/
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthBurstThrottle, AuthSustainedThrottle])
def register_view(request):
    """Register a new user account and return JWT tokens."""
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            message="Validation failed.",
            code="VALIDATION_ERROR",
            details=serializer.errors,
        )

    user, tokens = register_user(
        email=serializer.validated_data["email"],
        password=serializer.validated_data["password"],
        full_name=serializer.validated_data.get("full_name", ""),
    )

    return created_response(
        data={
            "user": UserSerializer(user).data,
            "tokens": tokens,
        },
        message="Registration successful.",
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login/
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthBurstThrottle, AuthSustainedThrottle])
def login_view(request):
    """Authenticate user credentials and return JWT tokens."""
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            message="Validation failed.",
            code="VALIDATION_ERROR",
            details=serializer.errors,
        )

    user, result = authenticate_user(
        email=serializer.validated_data["email"],
        password=serializer.validated_data["password"],
    )

    if user is None:
        return error_response(
            message=result,
            code="AUTHENTICATION_FAILED",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    return success_response(
        data={
            "user": UserSerializer(user).data,
            "tokens": result,
        },
        message="Login successful.",
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/token/refresh/
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthBurstThrottle, AuthSustainedThrottle])
def token_refresh_view(request):
    """Refresh an access token using a valid refresh token."""
    serializer = TokenRefreshInputSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            message="Validation failed.",
            code="VALIDATION_ERROR",
            details=serializer.errors,
        )

    tokens, err = refresh_access_token(serializer.validated_data["refresh"])
    if err:
        return error_response(
            message=err,
            code="INVALID_TOKEN",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    return success_response(data={"tokens": tokens}, message="Token refreshed.")


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout/
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """Blacklist the refresh token to log the user out."""
    refresh_token = request.data.get("refresh")
    if not refresh_token:
        return error_response(message="Refresh token is required.", code="MISSING_TOKEN")

    ok, err = blacklist_refresh_token(refresh_token)
    if not ok:
        return error_response(message=err, code="INVALID_TOKEN")

    logger.info("User logged out: %s", request.user.email)
    return success_response(message="Logged out successfully.")


# ---------------------------------------------------------------------------
# GET / PATCH  /api/v1/auth/profile/
# ---------------------------------------------------------------------------
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def profile_view(request):
    """Retrieve or update the authenticated user's profile."""
    if request.method == "GET":
        return success_response(data=UserSerializer(request.user).data)

    # PATCH
    serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
    if not serializer.is_valid():
        return error_response(
            message="Validation failed.",
            code="VALIDATION_ERROR",
            details=serializer.errors,
        )
    serializer.save()
    return success_response(
        data=UserSerializer(request.user).data,
        message="Profile updated.",
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/change-password/
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    """Change the authenticated user's password."""
    serializer = ChangePasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            message="Validation failed.",
            code="VALIDATION_ERROR",
            details=serializer.errors,
        )

    ok, err = change_user_password(
        user=request.user,
        old_password=serializer.validated_data["old_password"],
        new_password=serializer.validated_data["new_password"],
    )
    if not ok:
        return error_response(message=err, code="INVALID_PASSWORD")

    return success_response(message="Password changed successfully.")
