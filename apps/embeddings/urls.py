"""
InsightScribe - Embedding URLs

Two URL sets:
- ``interview_urlpatterns`` — mounted at ``.../interviews/<interview_id>/embeddings/``
- ``project_urlpatterns``   — mounted at ``.../projects/<project_id>/embeddings/``
"""

from django.urls import path

from . import views

app_name = "embeddings"

# Interview-scoped endpoints (need interview_id in path)
interview_urlpatterns = [
    path("generate/", views.trigger_embedding_view, name="trigger-embedding"),
    path("stats/", views.embedding_stats_view, name="embedding-stats"),
]

# Project-scoped endpoints (need only project_id in path)
project_urlpatterns = [
    path("search/", views.similarity_search_view, name="similarity-search"),
]

# Default urlpatterns = interview_urlpatterns (for backward compat)
urlpatterns = interview_urlpatterns
