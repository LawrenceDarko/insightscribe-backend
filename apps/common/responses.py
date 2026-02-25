"""
InsightScribe - Standardized API Response Helpers
"""

from rest_framework import status
from rest_framework.response import Response


def success_response(data=None, message="Success", status_code=status.HTTP_200_OK):
    """Return a standardized success JSON response."""
    payload = {
        "success": True,
        "message": message,
    }
    if data is not None:
        payload["data"] = data
    return Response(payload, status=status_code)


def created_response(data=None, message="Created successfully"):
    """Return a 201 Created response."""
    return success_response(data=data, message=message, status_code=status.HTTP_201_CREATED)


def error_response(message="An error occurred", code="ERROR", details=None, status_code=status.HTTP_400_BAD_REQUEST):
    """Return a standardized error JSON response."""
    payload = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        payload["error"]["details"] = details
    return Response(payload, status=status_code)


def not_found_response(message="Resource not found"):
    """Return a 404 response."""
    return error_response(message=message, code="NOT_FOUND", status_code=status.HTTP_404_NOT_FOUND)


def forbidden_response(message="You do not have permission to perform this action"):
    """Return a 403 response."""
    return error_response(message=message, code="FORBIDDEN", status_code=status.HTTP_403_FORBIDDEN)
