"""
InsightScribe - Centralized Exception Handler
Custom DRF exception handler for standardized JSON error responses.
"""

import logging
import traceback

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("apps")


def custom_exception_handler(exc, context):
    """
    Centralized exception handler that returns consistent JSON error responses.

    Format:
    {
        "success": false,
        "error": {
            "code": "ERROR_CODE",
            "message": "Human-readable message",
            "details": {} | []
        }
    }
    """
    # Let DRF handle its known exceptions first
    response = exception_handler(exc, context)

    if response is not None:
        error_payload = _build_error_payload(exc, response)
        response.data = error_payload
        return response

    # Handle Django-native exceptions not caught by DRF
    if isinstance(exc, Http404):
        return Response(
            _format_error("NOT_FOUND", "The requested resource was not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, PermissionDenied):
        return Response(
            _format_error("PERMISSION_DENIED", "You do not have permission to perform this action."),
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, ValidationError):
        return Response(
            _format_error("VALIDATION_ERROR", str(exc), details=exc.message_dict if hasattr(exc, "message_dict") else None),
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Unhandled exceptions — log and return 500
    logger.error(
        "Unhandled exception: %s\n%s",
        str(exc),
        traceback.format_exc(),
    )
    return Response(
        _format_error("INTERNAL_ERROR", "An unexpected error occurred. Please try again later."),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _build_error_payload(exc, response):
    """Build standardized error payload from DRF response."""
    code = _get_error_code(response.status_code)
    message = _extract_message(response.data)
    details = response.data if isinstance(response.data, (dict, list)) else None

    return _format_error(code, message, details)


def _format_error(code, message, details=None):
    """Return standardized error envelope."""
    error = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        error["error"]["details"] = details
    return error


def _get_error_code(status_code):
    """Map HTTP status code to error code string."""
    mapping = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
    }
    return mapping.get(status_code, "ERROR")


def _extract_message(data):
    """Extract human-readable message from DRF error data."""
    if isinstance(data, str):
        return data
    if isinstance(data, list) and data:
        return str(data[0])
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        # Return first field error
        for key, value in data.items():
            if isinstance(value, list) and value:
                return f"{key}: {value[0]}"
            return f"{key}: {value}"
    return "An error occurred."
