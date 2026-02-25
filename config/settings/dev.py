"""
InsightScribe - Development Settings
"""

from .base import *  # noqa: F401, F403

# ============================================
# DEBUG
# ============================================
DEBUG = True

# ============================================
# ALLOWED HOSTS
# ============================================
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# ============================================
# CORS (allow all in dev)
# ============================================
CORS_ALLOW_ALL_ORIGINS = True

# ============================================
# REST FRAMEWORK (add browsable API in dev)
# ============================================
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)

# ============================================
# THROTTLING (relaxed in dev)
# ============================================
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    "anon": "1000/min",
    "user": "5000/min",
    "auth_burst": "100/min",
    "auth_sustained": "1000/hour",
}

# ============================================
# LOGGING (verbose in dev)
# ============================================
LOGGING["root"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405

# ============================================
# CELERY (run tasks synchronously in dev — no worker needed)
# ============================================
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# ============================================
# EMAIL (console backend in dev)
# ============================================
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
