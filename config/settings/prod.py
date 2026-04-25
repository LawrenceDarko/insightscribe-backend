"""
InsightScribe - Production Settings
"""

import os

from decouple import Csv, config

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
configured_hosts = config("DJANGO_ALLOWED_HOSTS", default="", cast=Csv())
ALLOWED_HOSTS = [host for host in configured_hosts if host]

# Railway deployments can rotate generated subdomains between releases.
ALLOWED_HOSTS.append(".up.railway.app")

railway_public_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
if railway_public_domain:
    ALLOWED_HOSTS.append(railway_public_domain)

# Keep order stable while removing duplicates.
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))

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

# Prefer stdout logging on Railway-style ephemeral filesystems.
if config("ENABLE_FILE_LOGGING", default=False, cast=bool):
    LOGGING["handlers"]["file"]["filename"] = config(  # noqa: F405
        "FILE_LOG_PATH",
        default="/tmp/insightscribe.log",
    )
else:
    LOGGING["root"]["handlers"] = ["console"]  # noqa: F405
    LOGGING["loggers"]["django.request"]["handlers"] = ["console"]  # noqa: F405
    LOGGING["loggers"]["apps"]["handlers"] = ["console"]  # noqa: F405
