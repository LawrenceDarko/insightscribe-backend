"""
InsightScribe - Chat Service
Manages conversational context and integrates with the RAG engine.

Design:
- Each ``ChatSession`` groups an exchange of messages between a user and the
  assistant, scoped to a single project.
- Prior messages are loaded from the DB and trimmed to fit
  ``MAX_HISTORY_MESSAGES`` (most-recent-first) before being injected into the
  LLM context via ``rag_query(conversation_history=…)``.
- The assistant's answer, supporting quotes, and source references are
  persisted on every exchange for auditing and re-display.
"""

import logging

from django.conf import settings
from django.db.models import Count

from ..models import ChatMessage, ChatSession
from .rag_service import rag_query

logger = logging.getLogger("apps.rag")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Max *pairs* of messages (user + assistant) to include as LLM history.
# Actual message rows = MAX_HISTORY_MESSAGES * 2.
MAX_HISTORY_MESSAGES: int = getattr(settings, "RAG_MAX_HISTORY_MESSAGES", 20)

# Rough per-message token cap when budgeting history for the context window.
MAX_HISTORY_TOKEN_BUDGET: int = getattr(settings, "RAG_MAX_HISTORY_TOKEN_BUDGET", 3000)


# ============================================================================
# Public: conversational chat
# ============================================================================
def chat_with_project(
    project,
    user,
    question: str,
    session_id=None,
) -> dict:
    """
    Conversational chat with project interviews.

    1. Get or create chat session
    2. Load trimmed conversation history
    3. Store the user's question
    4. Run RAG query **with** history for conversational context
    5. Store the assistant's answer + sources + quotes
    6. Return structured response
    """
    # 1. Session
    session = _get_or_create_session(project, user, session_id)

    # 2. Build OpenAI-format history from prior messages
    history = _build_conversation_history(session)

    # 3. Persist user message
    user_msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.USER,
        content=question,
        token_count=_estimate_tokens(question),
    )

    # 4. RAG with history
    result = rag_query(
        project_id=str(project.id),
        question=question,
        user=user,
        conversation_history=history,
    )

    # 5. Persist assistant message
    answer_text = result["answer"]
    assistant_msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content=answer_text,
        sources=result.get("sources", []),
        supporting_quotes=result.get("supporting_quotes", []),
        token_count=_estimate_tokens(answer_text),
    )

    # Auto-title from first question
    if session.title == "New Chat":
        session.title = question[:80]
        session.save(update_fields=["title", "updated_at"])

    # 6. Return
    return {
        "session_id": str(session.id),
        "message_id": assistant_msg.id,
        "answer": answer_text,
        "supporting_quotes": result.get("supporting_quotes", []),
        "sources": result.get("sources", []),
        "question": question,
        "elapsed_seconds": result.get("elapsed_seconds"),
    }


# ============================================================================
# Public: session listing
# ============================================================================
def get_chat_sessions(project, user):
    """
    Return all chat sessions for a user in a project with an annotated
    ``message_count`` (single query, no N+1).
    """
    return (
        ChatSession.objects.filter(
            project=project,
            user=user,
            is_deleted=False,
        )
        .annotate(message_count=Count("messages"))
        .order_by("-updated_at")
        .only("id", "project_id", "title", "created_at", "updated_at")
    )


# ============================================================================
# Public: history retrieval
# ============================================================================
def get_chat_history(session_id, user, project=None):
    """
    Return the full ordered message history for a chat session.
    Returns ``None`` if the session does not exist or belongs to another user.
    """
    filter_kwargs = {
        "id": session_id,
        "user": user,
        "is_deleted": False,
    }
    if project is not None:
        filter_kwargs["project"] = project

    try:
        session = ChatSession.objects.get(**filter_kwargs)
    except ChatSession.DoesNotExist:
        return None

    return session.messages.order_by("created_at")


# ============================================================================
# Public: session lifecycle
# ============================================================================
def delete_chat_session(session_id, user, project=None) -> bool:
    """
    Soft-delete a chat session.  Returns ``True`` on success.
    """
    filter_kwargs = {
        "id": session_id,
        "user": user,
        "is_deleted": False,
    }
    if project is not None:
        filter_kwargs["project"] = project

    try:
        session = ChatSession.objects.get(**filter_kwargs)
    except ChatSession.DoesNotExist:
        return False

    session.soft_delete()
    logger.info("Chat session soft-deleted: %s (user: %s)", session_id, user.id)
    return True


def rename_chat_session(session_id, user, new_title: str, project=None) -> dict | None:
    """
    Rename a chat session.  Returns updated session dict, or ``None`` if not
    found.
    """
    filter_kwargs = {
        "id": session_id,
        "user": user,
        "is_deleted": False,
    }
    if project is not None:
        filter_kwargs["project"] = project

    try:
        session = ChatSession.objects.get(**filter_kwargs)
    except ChatSession.DoesNotExist:
        return None

    session.title = new_title[:255]
    session.save(update_fields=["title", "updated_at"])
    logger.info("Chat session renamed: %s → '%s'", session_id, new_title[:80])
    return {
        "session_id": str(session.id),
        "title": session.title,
    }


# ============================================================================
# Internal helpers
# ============================================================================
def _get_or_create_session(project, user, session_id=None):
    """Retrieve an existing session or create a new one."""
    if session_id:
        try:
            return ChatSession.objects.get(
                id=session_id,
                project=project,
                user=user,
                is_deleted=False,
            )
        except ChatSession.DoesNotExist:
            logger.warning(
                "Chat session %s not found for user %s — creating new session",
                session_id, user.id,
            )

    session = ChatSession.objects.create(project=project, user=user)
    logger.info("New chat session: %s (project: %s, user: %s)", session.id, project.id, user.id)
    return session


def _build_conversation_history(session) -> list[dict]:
    """
    Fetch the most recent messages from the session and format them as an
    OpenAI-compatible messages list (``[{"role": …, "content": …}, …]``).

    Respects both a row-count limit (``MAX_HISTORY_MESSAGES * 2``) and a rough
    token budget (``MAX_HISTORY_TOKEN_BUDGET``) to avoid overflowing the LLM
    context window together with the transcript excerpts.
    """
    row_limit = MAX_HISTORY_MESSAGES * 2
    recent_msgs = list(
        ChatMessage.objects.filter(session=session)
        .order_by("-created_at")
        .values("role", "content", "token_count")[:row_limit]
    )

    if not recent_msgs:
        return []

    # Reverse so chronological
    recent_msgs.reverse()

    # Trim to token budget
    history: list[dict] = []
    token_total = 0
    for msg in recent_msgs:
        tokens = msg["token_count"] or _estimate_tokens(msg["content"])
        if token_total + tokens > MAX_HISTORY_TOKEN_BUDGET and history:
            break
        history.append({"role": msg["role"], "content": msg["content"]})
        token_total += tokens

    return history


def _estimate_tokens(text: str) -> int:
    """Rough token count: ~1 token per 4 characters (English approximation)."""
    return max(len(text) // 4, 1)
