"""
InsightScribe - RAG / Chat URLs
"""

from django.urls import path

from . import views

app_name = "rag"

urlpatterns = [
    # One-shot RAG
    path("query/", views.rag_query_view, name="rag-query"),

    # Conversational chat
    path("chat/", views.chat_view, name="chat"),

    # Session management
    path("chat/sessions/", views.chat_sessions_view, name="chat-sessions"),
    path("chat/sessions/<uuid:session_id>/", views.chat_history_view, name="chat-history"),
    path("chat/sessions/<uuid:session_id>/delete/", views.delete_chat_session_view, name="chat-session-delete"),
    path("chat/sessions/<uuid:session_id>/rename/", views.rename_chat_session_view, name="chat-session-rename"),
]
