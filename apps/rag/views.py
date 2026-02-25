"""
InsightScribe - RAG / Chat Views (Function-Based)
Endpoints for one-shot RAG queries and conversational chat sessions.
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.common.responses import error_response, not_found_response, success_response
from apps.projects.services.project_service import get_project_for_user

from .serializers import (
    ChatMessageSerializer,
    ChatQuerySerializer,
    ChatResponseSerializer,
    ChatSessionSerializer,
    RAGQuerySerializer,
    RAGResponseSerializer,
    RenameSessionSerializer,
)
from .services.chat_service import (
    chat_with_project,
    delete_chat_session,
    get_chat_history,
    get_chat_sessions,
    rename_chat_session,
)
from .services.rag_service import rag_query

logger = logging.getLogger("apps.rag")


# ---------------------------------------------------------------------------
# POST  .../query/   — one-shot RAG (no session, no history)
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rag_query_view(request, project_id):
    """One-shot RAG query against all embedded interviews in a project."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    serializer = RAGQuerySerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            message="Validation failed.",
            code="VALIDATION_ERROR",
            details=serializer.errors,
        )

    try:
        result = rag_query(
            project_id=str(project.id),
            question=serializer.validated_data["question"],
            user=request.user,
        )
    except RuntimeError as exc:
        logger.error("RAG query error for project %s: %s", project_id, exc)
        return error_response(
            message=str(exc),
            code="RAG_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    response_serializer = RAGResponseSerializer(result)
    return success_response(data=response_serializer.data)


# ---------------------------------------------------------------------------
# POST  .../chat/   — conversational chat (with session & history)
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_view(request, project_id):
    """
    Conversational chat with project interviews.

    Accepts an optional ``session_id`` to continue an existing conversation.
    If omitted, a new session is created automatically.
    """
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    serializer = ChatQuerySerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            message="Validation failed.",
            code="VALIDATION_ERROR",
            details=serializer.errors,
        )

    try:
        result = chat_with_project(
            project=project,
            user=request.user,
            question=serializer.validated_data["question"],
            session_id=serializer.validated_data.get("session_id"),
        )
    except RuntimeError as exc:
        logger.error("Chat error for project %s: %s", project_id, exc)
        return error_response(
            message=str(exc),
            code="RAG_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    response_serializer = ChatResponseSerializer(result)
    return success_response(data=response_serializer.data)


# ---------------------------------------------------------------------------
# GET  .../chat/sessions/   — list chat sessions
# ---------------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def chat_sessions_view(request, project_id):
    """List all chat sessions for the current user in a project."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    sessions = get_chat_sessions(project, request.user)
    serializer = ChatSessionSerializer(sessions, many=True)
    return success_response(data=serializer.data)


# ---------------------------------------------------------------------------
# GET  .../chat/sessions/<session_id>/   — retrieve full chat history
# ---------------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def chat_history_view(request, project_id, session_id):
    """Retrieve the full ordered message history for a chat session."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    messages = get_chat_history(session_id, request.user, project=project)
    if messages is None:
        return not_found_response("Chat session not found.")

    serializer = ChatMessageSerializer(messages, many=True)
    return success_response(data=serializer.data)


# ---------------------------------------------------------------------------
# DELETE  .../chat/sessions/<session_id>/   — soft-delete a session
# ---------------------------------------------------------------------------
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_chat_session_view(request, project_id, session_id):
    """Soft-delete a chat session and all its messages."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    deleted = delete_chat_session(session_id, request.user, project=project)
    if not deleted:
        return not_found_response("Chat session not found.")

    return success_response(
        message="Chat session deleted.",
        status_code=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# PATCH  .../chat/sessions/<session_id>/   — rename a session
# ---------------------------------------------------------------------------
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def rename_chat_session_view(request, project_id, session_id):
    """Rename a chat session."""
    project = get_project_for_user(project_id, request.user)
    if not project:
        return not_found_response("Project not found.")

    serializer = RenameSessionSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            message="Validation failed.",
            code="VALIDATION_ERROR",
            details=serializer.errors,
        )

    result = rename_chat_session(
        session_id,
        request.user,
        new_title=serializer.validated_data["title"],
        project=project,
    )
    if result is None:
        return not_found_response("Chat session not found.")

    return success_response(data=result)
