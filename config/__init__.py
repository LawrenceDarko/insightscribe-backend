"""
InsightScribe Django config package.

Import the Celery app so that ``@shared_task`` decorators are
registered when Django starts and ``autodiscover_tasks()`` fires.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
