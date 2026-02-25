"""
InsightScribe - RAG Query Engine
Production-grade semantic search + LLM synthesis for project-level Q&A.

Pipeline:
1. Generate embedding for the user question
2. pgvector cosine-similarity search across ALL chunks in the project
3. Retrieve top-k matches and build a context window
4. Send context + question to OpenAI for synthesis
5. Return structured answer with supporting quotes, timestamps & interview refs
"""

import json
import logging
import time

from django.conf import settings
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from apps.embeddings.services.embedding_service import (
    generate_query_embedding,
    similarity_search,
)

logger = logging.getLogger("apps.rag")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
RAG_TOP_K: int = getattr(settings, "RAG_TOP_K", 10)
RAG_SCORE_THRESHOLD: float = getattr(settings, "RAG_SCORE_THRESHOLD", 0.25)
RAG_MAX_CONTEXT_TOKENS: int = getattr(settings, "RAG_MAX_CONTEXT_TOKENS", 6000)
RAG_LLM_TEMPERATURE: float = getattr(settings, "RAG_LLM_TEMPERATURE", 0.3)
RAG_LLM_MAX_TOKENS: int = getattr(settings, "RAG_LLM_MAX_TOKENS", 2000)
RAG_LLM_MAX_RETRIES: int = getattr(settings, "RAG_LLM_MAX_RETRIES", 3)
RAG_LLM_RETRY_BASE_DELAY: float = getattr(settings, "RAG_LLM_RETRY_BASE_DELAY", 2.0)

_RETRIABLE = (APIConnectionError, APITimeoutError, RateLimitError)

# Module-level OpenAI client (lazy singleton)
_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


# ---------------------------------------------------------------------------
# System prompt — instructs structured JSON output
# ---------------------------------------------------------------------------
RAG_SYSTEM_PROMPT = """\
You are an expert research analyst helping users extract insights from interview transcripts.

RULES:
- Answer ONLY based on the provided transcript excerpts.
- If the excerpts do not contain relevant information, say so clearly.
- Always cite your sources using the interview title, timestamps, and speaker label.
- Be concise and well-structured.
- Use bullet points for multiple findings.

You MUST return a valid JSON object with EXACTLY this structure (no markdown, no extra text):
{
  "answer": "Your synthesized answer here.",
  "supporting_quotes": [
    {
      "text": "Exact quote from the transcript",
      "interview_title": "Title of the interview",
      "start_time": 12.5,
      "end_time": 30.0,
      "speaker": "Speaker label or empty string"
    }
  ]
}

IMPORTANT:
- Include 1-5 of the most relevant supporting quotes.
- Each quote must come verbatim from the provided excerpts.
- The "answer" field must synthesize the evidence into a clear response.
"""


# ============================================================================
# Public: one-shot RAG query
# ============================================================================
def rag_query(
    project_id: str,
    question: str,
    user,
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Full RAG pipeline.

    Args:
        project_id: UUID of the project to search.
        question: The user's natural-language question.
        user: The authenticated Django user (for logging / audit).
        conversation_history: Optional list of prior ``{"role": …, "content": …}``
            message dicts to provide conversational context to the LLM.

    Returns a dict with keys:
      - ``answer``               – synthesized LLM answer
      - ``supporting_quotes``    – list of quote dicts with timestamps
      - ``sources``              – raw similarity-search matches
      - ``question``             – echo of the original question
      - ``result_count``         – number of chunks retrieved
      - ``elapsed_seconds``      – wall-clock time for the full pipeline
    """
    pipeline_start = time.monotonic()
    logger.info("RAG query START — project=%s question='%s'", project_id, question[:120])

    # 1. Generate query embedding ------------------------------------------------
    try:
        embed_start = time.monotonic()
        query_vector = generate_query_embedding(question)
        embed_elapsed = time.monotonic() - embed_start
        logger.debug("Query embedding generated in %.2fs", embed_elapsed)
    except Exception as exc:
        logger.error("Failed to embed query: %s", exc)
        raise RuntimeError("Failed to generate query embedding.") from exc

    # 2. Similarity search -------------------------------------------------------
    search_start = time.monotonic()
    matches = similarity_search(
        query_vector=query_vector,
        project_id=project_id,
        top_k=RAG_TOP_K,
        score_threshold=RAG_SCORE_THRESHOLD,
    )
    search_elapsed = time.monotonic() - search_start
    logger.debug("Similarity search returned %d matches in %.2fs", len(matches), search_elapsed)

    if not matches:
        elapsed = time.monotonic() - pipeline_start
        return {
            "answer": "No relevant information found in the project interviews.",
            "supporting_quotes": [],
            "sources": [],
            "question": question,
            "result_count": 0,
            "elapsed_seconds": round(elapsed, 2),
        }

    # 3. Build context window (respect token budget) -----------------------------
    context, included_matches = _build_context(matches)

    # 4. LLM synthesis -----------------------------------------------------------
    synth_start = time.monotonic()
    llm_result = _synthesize_answer(question, context, conversation_history)
    synth_elapsed = time.monotonic() - synth_start
    logger.debug("LLM synthesis completed in %.2fs", synth_elapsed)

    # 5. Build structured response -----------------------------------------------
    sources = _format_sources(included_matches)

    elapsed = time.monotonic() - pipeline_start
    logger.info(
        "RAG query DONE — project=%s matches=%d elapsed=%.2fs",
        project_id, len(included_matches), elapsed,
    )

    return {
        "answer": llm_result["answer"],
        "supporting_quotes": llm_result["supporting_quotes"],
        "sources": sources,
        "question": question,
        "result_count": len(included_matches),
        "elapsed_seconds": round(elapsed, 2),
    }


# ============================================================================
# Internal: context construction
# ============================================================================
def _build_context(matches: list[dict]) -> tuple[str, list[dict]]:
    """
    Assemble a context string from retrieved chunks while staying within
    the configured token budget (approximated as ``len(text.split())``).

    Returns ``(context_string, list_of_included_matches)``.
    """
    context_parts: list[str] = []
    included: list[dict] = []
    token_budget = RAG_MAX_CONTEXT_TOKENS
    token_count = 0

    for m in matches:
        # Rough token estimate (words ≈ 0.75 tokens, but close enough for budgeting)
        chunk_tokens = m.get("token_count", 0) or len(m["text"].split())
        if token_count + chunk_tokens > token_budget and included:
            break  # stop adding more — but always include at least one

        speaker_part = f", Speaker: {m['speaker_label']}" if m.get("speaker_label") else ""
        start = m["start_time"] if m["start_time"] is not None else 0
        end = m["end_time"] if m["end_time"] is not None else 0

        part = (
            f"[Interview: {m['interview_title']}, "
            f"Time: {start:.1f}s–{end:.1f}s"
            f"{speaker_part}]\n"
            f"{m['text']}"
        )
        context_parts.append(part)
        included.append(m)
        token_count += chunk_tokens

    return "\n\n---\n\n".join(context_parts), included


def _format_sources(matches: list[dict]) -> list[dict]:
    """Transform raw similarity-search dicts into a cleaner source format."""
    return [
        {
            "chunk_id": m["chunk_id"],
            "interview_id": m["interview_id"],
            "interview_title": m["interview_title"],
            "text": m["text"],
            "start_time": m["start_time"],
            "end_time": m["end_time"],
            "chunk_index": m["chunk_index"],
            "speaker": m.get("speaker_label", ""),
            "similarity": m["similarity"],
        }
        for m in matches
    ]


# ============================================================================
# Internal: LLM synthesis with retries
# ============================================================================
def _synthesize_answer(
    question: str,
    context: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Call OpenAI chat-completion to synthesize an answer from the context.
    Parses the JSON-structured response. Retries on transient API errors.

    Args:
        question: The current user question.
        context: Formatted transcript excerpts.
        conversation_history: Optional list of prior ``{"role": …, "content": …}``
            dicts for conversational continuity.

    Returns ``{"answer": str, "supporting_quotes": list[dict]}``.
    """
    client = _get_openai_client()

    messages: list[dict] = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]

    # Inject conversation history (trimmed to stay within budget)
    if conversation_history:
        messages.extend(conversation_history)

    messages.append(
        {
            "role": "user",
            "content": (
                f"Transcript excerpts:\n\n{context}\n\n"
                f"---\n\n"
                f"Question: {question}"
            ),
        },
    )

    for attempt in range(1, RAG_LLM_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=settings.OPENAI_CHAT_MODEL,
                messages=messages,
                temperature=RAG_LLM_TEMPERATURE,
                max_tokens=RAG_LLM_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            return _parse_llm_response(raw)

        except _RETRIABLE as exc:
            delay = RAG_LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "LLM transient error (attempt %d/%d), retrying in %.1fs: %s",
                attempt, RAG_LLM_MAX_RETRIES, delay, exc,
            )
            if attempt < RAG_LLM_MAX_RETRIES:
                time.sleep(delay)
            else:
                logger.error("LLM exhausted all %d retries", RAG_LLM_MAX_RETRIES)
                return _fallback_response("The AI service is temporarily unavailable. Please try again.")

        except Exception as exc:
            logger.error("LLM non-retriable error: %s", exc)
            return _fallback_response("An error occurred while generating the answer. Please try again.")

    return _fallback_response("The AI service is temporarily unavailable. Please try again.")  # pragma: no cover


def _parse_llm_response(raw: str) -> dict:
    """Parse the JSON response from the LLM, with a graceful fallback."""
    try:
        data = json.loads(raw)
        answer = data.get("answer", raw)
        quotes = data.get("supporting_quotes", [])

        # Normalise each quote to expected shape
        normalised_quotes = []
        for q in quotes:
            if not isinstance(q, dict):
                continue
            normalised_quotes.append({
                "text": q.get("text", ""),
                "interview_title": q.get("interview_title", ""),
                "start_time": q.get("start_time"),
                "end_time": q.get("end_time"),
                "speaker": q.get("speaker", ""),
            })

        return {"answer": answer, "supporting_quotes": normalised_quotes}

    except (json.JSONDecodeError, TypeError, KeyError):
        logger.warning("LLM returned non-JSON response, using raw text as answer")
        return {"answer": raw, "supporting_quotes": []}


def _fallback_response(message: str) -> dict:
    """Return a safe fallback when LLM synthesis fails."""
    return {"answer": message, "supporting_quotes": []}
