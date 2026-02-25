"""
InsightScribe - Authentication Decorators
Reusable decorators for protecting endpoints.
"""

import functools
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken

logger = logging.getLogger("apps.accounts")


def token_required(fn):
    """
    Decorator for function-based views that enforces JWT authentication.

    Usage::

        @api_view(["GET"])
        @token_required
        def my_protected_view(request):
            ...

    On failure returns a standardized JSON error response with 401 status.
    On success, populates ``request.user`` and ``request.auth`` before calling
    the wrapped view.
    """

    @functools.wraps(fn)
    def wrapper(request, *args, **kwargs):
        authenticator = JWTAuthentication()
        try:
            result = authenticator.authenticate(request)
        except (AuthenticationFailed, InvalidToken) as exc:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": str(exc.detail) if hasattr(exc, "detail") else "Authentication credentials were not provided or are invalid.",
                    },
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if result is None:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Authentication credentials were not provided.",
                    },
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        request.user, request.auth = result
        return fn(request, *args, **kwargs)

    return wrapper


def plan_required(allowed_plans):
    """
    Decorator that restricts access to users with specific plans.

    Usage::

        @api_view(["POST"])
        @token_required
        @plan_required(["pro"])
        def pro_only_view(request):
            ...
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(request, *args, **kwargs):
            if not hasattr(request, "user") or not request.user.is_authenticated:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "UNAUTHORIZED",
                            "message": "Authentication required.",
                        },
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            if request.user.plan not in allowed_plans:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "PLAN_REQUIRED",
                            "message": f"This feature requires one of the following plans: {', '.join(allowed_plans)}.",
                        },
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            return fn(request, *args, **kwargs)

        return wrapper

    return decorator
