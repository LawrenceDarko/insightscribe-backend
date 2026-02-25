"""
InsightScribe - Custom Middleware
"""

import logging
import time
import traceback

from django.http import JsonResponse

logger = logging.getLogger("apps")


class RequestLoggingMiddleware:
    """Logs every request with method, path, status, and duration."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            "%s %s %s %.2fms",
            request.method,
            request.get_full_path(),
            response.status_code,
            duration_ms,
        )
        response["X-Request-Duration-Ms"] = f"{duration_ms:.2f}"
        return response


class ExceptionHandlerMiddleware:
    """
    Catch-all middleware for any unhandled exceptions that slip past DRF.
    Returns a consistent JSON 500 response.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        logger.error(
            "Unhandled middleware exception on %s %s: %s\n%s",
            request.method,
            request.get_full_path(),
            str(exception),
            traceback.format_exc(),
        )
        return JsonResponse(
            {
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                },
            },
            status=500,
        )
