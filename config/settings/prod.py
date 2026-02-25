"""
InsightScribe - Production Settings
"""

from decouple import config

from .base import *  # noqa: F401, F403

# ============================================
# DEBUG
# ============================================
DEBUG = False

# ============================================
# SECURITY
# ============================================
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ============================================
# ALLOWED HOSTS
# ============================================
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", cast=Csv())  # noqa: F405

# ============================================
# DATABASE (production pool settings)
# ============================================
DATABASES["default"]["CONN_MAX_AGE"] = 600  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405

# ============================================
# CACHES (Redis)
# ============================================
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("CELERY_BROKER_URL", default="redis://localhost:6379/0"),
    }
}

# ============================================
# LOGGING (structured for production)
# ============================================
LOGGING["root"]["level"] = "WARNING"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "INFO"  # noqa: F405
LOGGING["handlers"]["file"]["filename"] = "/var/log/insightscribe/app.log"  # noqa: F405
