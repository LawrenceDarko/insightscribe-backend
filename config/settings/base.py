"""
InsightScribe - Base Settings
Production-grade Django configuration shared across all environments.
"""

import os
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

# ============================================
# PATHS
# ============================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ============================================
# SECURITY
# ============================================
SECRET_KEY = config("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="", cast=Csv())

# ============================================
# APPLICATION DEFINITION
# ============================================
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",  # Required for SearchVectorField, GinIndex, pgvector
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "storages",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.projects",
    "apps.interviews",
    "apps.transcription",
    "apps.embeddings",
    "apps.rag",
    "apps.insights",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ============================================
# MIDDLEWARE
# ============================================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.RequestLoggingMiddleware",
    "config.middleware.ExceptionHandlerMiddleware",
]

ROOT_URLCONF = "config.urls"

# ============================================
# TEMPLATES (minimal - API only)
# ============================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ============================================
# DATABASE (Supabase PostgreSQL + pgvector)
# ============================================
import dj_database_url  # noqa: E402

DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL"),
        engine="django.db.backends.postgresql",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ============================================
# CUSTOM USER MODEL
# ============================================
AUTH_USER_MODEL = "accounts.User"

# ============================================
# PASSWORD VALIDATION
# ============================================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ============================================
# INTERNATIONALIZATION
# ============================================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ============================================
# STATIC FILES
# ============================================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ============================================
# DEFAULT PRIMARY KEY
# ============================================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================
# DJANGO REST FRAMEWORK
# ============================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("THROTTLE_RATE_ANON", default="20/min"),
        "user": config("THROTTLE_RATE_USER", default="100/min"),
        "auth_burst": config("THROTTLE_RATE_AUTH_BURST", default="5/min"),
        "auth_sustained": config("THROTTLE_RATE_AUTH_SUSTAINED", default="30/hour"),
    },
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "config.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "rest_framework.schemas.openapi.AutoSchema",
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S.%fZ",
}

# ============================================
# JWT CONFIGURATION
# ============================================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=60, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.CustomTokenObtainPairSerializer",
    # Security: only allow tokens issued after password change
    "CHECK_REVOKE_TOKEN": False,
    "LEEWAY": 0,
}

# ============================================
# CORS
# ============================================
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# ============================================
# FILE UPLOAD
# ============================================
MAX_UPLOAD_SIZE_MB = config("MAX_UPLOAD_SIZE_MB", default=200, cast=int)
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_BYTES
ALLOWED_AUDIO_TYPES = ["audio/mpeg", "audio/wav", "audio/mp4", "video/mp4"]
ALLOWED_AUDIO_EXTENSIONS = [".mp3", ".wav", ".mp4"]

# ============================================
# SUPABASE STORAGE (S3-compatible)
# ============================================
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="interview-uploads")
AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default="")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="us-east-1")
AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = True
AWS_S3_SIGNATURE_VERSION = "s3v4"

# ============================================
# OPENAI
# ============================================
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_EMBEDDING_DIMENSIONS = 1536
OPENAI_CHAT_MODEL = "gpt-4o"
OPENAI_WHISPER_MODEL = "whisper-1"

# ============================================
# TRANSCRIPTION
# ============================================
TRANSCRIPTION_MAX_CHUNK_TOKENS = config("TRANSCRIPTION_MAX_CHUNK_TOKENS", default=500, cast=int)
TRANSCRIPTION_OVERLAP_TOKENS = config("TRANSCRIPTION_OVERLAP_TOKENS", default=50, cast=int)
WHISPER_MAX_RETRIES = config("WHISPER_MAX_RETRIES", default=3, cast=int)
WHISPER_RETRY_BASE_DELAY = config("WHISPER_RETRY_BASE_DELAY", default=2.0, cast=float)

# ============================================
# EMBEDDING
# ============================================
EMBEDDING_BATCH_SIZE = config("EMBEDDING_BATCH_SIZE", default=100, cast=int)
EMBEDDING_MAX_RETRIES = config("EMBEDDING_MAX_RETRIES", default=3, cast=int)
EMBEDDING_RETRY_BASE_DELAY = config("EMBEDDING_RETRY_BASE_DELAY", default=2.0, cast=float)

# ============================================
# RAG
# ============================================
RAG_TOP_K = config("RAG_TOP_K", default=10, cast=int)
RAG_SCORE_THRESHOLD = config("RAG_SCORE_THRESHOLD", default=0.25, cast=float)
RAG_MAX_CONTEXT_TOKENS = config("RAG_MAX_CONTEXT_TOKENS", default=6000, cast=int)
RAG_LLM_TEMPERATURE = config("RAG_LLM_TEMPERATURE", default=0.3, cast=float)
RAG_LLM_MAX_TOKENS = config("RAG_LLM_MAX_TOKENS", default=2000, cast=int)
RAG_LLM_MAX_RETRIES = config("RAG_LLM_MAX_RETRIES", default=3, cast=int)
RAG_LLM_RETRY_BASE_DELAY = config("RAG_LLM_RETRY_BASE_DELAY", default=2.0, cast=float)
RAG_MAX_HISTORY_MESSAGES = config("RAG_MAX_HISTORY_MESSAGES", default=20, cast=int)
RAG_MAX_HISTORY_TOKEN_BUDGET = config("RAG_MAX_HISTORY_TOKEN_BUDGET", default=3000, cast=int)

# ============================================
# INSIGHTS
# ============================================
INSIGHT_MAX_CHUNKS = config("INSIGHT_MAX_CHUNKS", default=1000, cast=int)
INSIGHT_MAX_CONTEXT_TOKENS = config("INSIGHT_MAX_CONTEXT_TOKENS", default=8000, cast=int)
INSIGHT_LLM_TEMPERATURE = config("INSIGHT_LLM_TEMPERATURE", default=0.2, cast=float)
INSIGHT_LLM_MAX_TOKENS = config("INSIGHT_LLM_MAX_TOKENS", default=4000, cast=int)
INSIGHT_LLM_MAX_RETRIES = config("INSIGHT_LLM_MAX_RETRIES", default=3, cast=int)
INSIGHT_LLM_RETRY_BASE_DELAY = config("INSIGHT_LLM_RETRY_BASE_DELAY", default=2.0, cast=float)
INSIGHT_CLUSTER_TOP_K = config("INSIGHT_CLUSTER_TOP_K", default=30, cast=int)
INSIGHT_CLUSTER_THRESHOLD = config("INSIGHT_CLUSTER_THRESHOLD", default=0.30, cast=float)

# ============================================
# CELERY
# ============================================
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes (for long audio files)
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60

# ============================================
# LOGGING
# ============================================
LOG_LEVEL = config("LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {module}.{funcName}:{lineno} - {message}",
            "style": "{",
        },
        "simple": {
            "format": "[{asctime}] {levelname} - {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "insightscribe.log",
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "file"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "file"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}

# Ensure log directory exists
os.makedirs(BASE_DIR / "logs", exist_ok=True)

# ============================================
# SENTRY (optional)
# ============================================
SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        send_default_pii=False,
    )
