"""
InsightScribe - Insight Report Generator Service

Production-grade pipeline:
1. Aggregate transcript chunks across project (paginated, soft-delete aware)
2. Cluster semantically similar chunks via pgvector cosine distance
3. Calculate frequency per cluster
4. Compute sentiment distribution
5. Generate structured report via LLM (retries, JSON output, token budgeting)
6. Return ranked themes with frequency, sentiment, and supporting quotes
"""

import json
import logging
import time
from collections import defaultdict

from django.conf import settings
from django.db.models import Avg, Count, F, Q
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from apps.embeddings.models import Embedding
from apps.embeddings.services.embedding_service import generate_query_embedding
from apps.transcription.models import TranscriptChunk

from ..models import InsightReport, ReportStatus, ReportType

logger = logging.getLogger("apps.insights")

# ---------------------------------------------------------------------------
# Configuration (from settings, with safe defaults)
# ---------------------------------------------------------------------------
INSIGHT_MAX_CHUNKS: int = getattr(settings, "INSIGHT_MAX_CHUNKS", 1000)
INSIGHT_MAX_CONTEXT_TOKENS: int = getattr(settings, "INSIGHT_MAX_CONTEXT_TOKENS", 8000)
INSIGHT_LLM_TEMPERATURE: float = getattr(settings, "INSIGHT_LLM_TEMPERATURE", 0.2)
INSIGHT_LLM_MAX_TOKENS: int = getattr(settings, "INSIGHT_LLM_MAX_TOKENS", 4000)
INSIGHT_LLM_MAX_RETRIES: int = getattr(settings, "INSIGHT_LLM_MAX_RETRIES", 3)
INSIGHT_LLM_RETRY_BASE_DELAY: float = getattr(settings, "INSIGHT_LLM_RETRY_BASE_DELAY", 2.0)
INSIGHT_CLUSTER_TOP_K: int = getattr(settings, "INSIGHT_CLUSTER_TOP_K", 30)
INSIGHT_CLUSTER_THRESHOLD: float = getattr(settings, "INSIGHT_CLUSTER_THRESHOLD", 0.30)
INSIGHT_FULL_PER_INTERVIEW_TOKEN_CAP: int = getattr(
    settings,
    "INSIGHT_FULL_PER_INTERVIEW_TOKEN_CAP",
    180,
)

_RETRIABLE = (APIConnectionError, APITimeoutError, RateLimitError)

# Module-level OpenAI client (lazy singleton)
_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


# ---------------------------------------------------------------------------
# Report type definitions — prompts & cluster seed queries
# ---------------------------------------------------------------------------
REPORT_CONFIGS = {
    ReportType.FEATURE_REQUESTS: {
        "title": "Top Feature Requests",
        "instruction": (
            "Analyze the following interview transcript excerpts and identify the top feature requests "
            "mentioned by interviewees. Rank them by frequency and urgency. "
            "Focus on concrete wishes, suggestions, and 'I wish' statements."
        ),
        "seed_queries": [
            "feature request or new functionality suggestion",
            "I wish the product had this feature",
            "it would be great if we could do this",
        ],
    },
    ReportType.FRUSTRATIONS: {
        "title": "Most Common Frustrations",
        "instruction": (
            "Analyze the following interview transcript excerpts and identify the most common frustrations, "
            "pain points, and complaints mentioned by interviewees. Rank by severity and frequency."
        ),
        "seed_queries": [
            "frustration pain point annoyance with the product",
            "this doesn't work well or is confusing",
            "I hate this or it drives me crazy",
        ],
    },
    ReportType.POSITIVE_THEMES: {
        "title": "Positive Themes",
        "instruction": (
            "Analyze the following interview transcript excerpts and identify positive themes, "
            "praise, and things interviewees appreciate. Rank by frequency."
        ),
        "seed_queries": [
            "positive feedback praise appreciation for the product",
            "I love this feature or this works great",
            "this is my favourite part of the product",
        ],
    },
    ReportType.NEGATIVE_THEMES: {
        "title": "Negative Themes",
        "instruction": (
            "Analyze the following interview transcript excerpts and identify negative themes, "
            "criticisms, and areas of dissatisfaction. Rank by frequency and impact."
        ),
        "seed_queries": [
            "negative feedback criticism complaint about the product",
            "this is bad or terrible or awful",
            "I would not recommend this because of these reasons",
        ],
    },
    ReportType.ONBOARDING: {
        "title": "Onboarding Issues",
        "instruction": (
            "Analyze the following interview transcript excerpts and identify onboarding-related issues, "
            "confusion during setup, and suggestions for improving the initial user experience."
        ),
        "seed_queries": [
            "confusing onboarding setup first-time experience",
            "getting started was difficult or unclear",
            "I didn't know how to begin or configure this",
        ],
    },
    ReportType.FULL: {
        "title": "Full Insight Report",
        "instruction": (
            "Analyze the following interview transcript excerpts comprehensively. "
            "Synthesize findings across all interviews represented in the excerpts, not just one conversation. "
            "Identify: (1) Top feature requests, (2) Common frustrations, (3) Positive themes, "
            "(4) Negative themes, (5) Onboarding issues. Rank each category by frequency."
        ),
        "seed_queries": [
            "feature request or new functionality they want",
            "frustration pain point annoyance problem",
            "positive praise good experience with the product",
            "negative criticism complaint dissatisfaction",
            "onboarding setup first-time confusion difficulty",
        ],
    },
}

SYSTEM_PROMPT = """\
You are an expert UX researcher analyzing interview transcripts.

Return your analysis as a JSON object with EXACTLY this structure (no markdown, no extra text):
{
    "themes": [
        {
            "rank": 1,
            "theme": "Theme name",
            "description": "2-3 sentence description synthesising the theme",
            "frequency": 5,
            "sentiment_avg": 0.3,
            "supporting_quotes": [
                {
                    "text": "Exact quote from provided transcript",
                    "interview_title": "Interview name",
                    "start_time": 12.5,
                    "end_time": 18.3,
                    "speaker": "Speaker label or empty string"
                }
            ]
        }
    ],
    "summary": "Executive summary of the key findings (3-5 sentences)",
    "total_chunks_analyzed": 150,
    "methodology": "Brief description of how the analysis was conducted"
}

RULES:
- Only use information from the provided transcript excerpts.
- Every supporting_quotes[].text MUST be a verbatim quote from the excerpts.
- Rank themes by frequency (most common first).
- Include sentiment_avg between -1.0 (very negative) and 1.0 (very positive).
- Include AT LEAST 2 and AT MOST 5 supporting quotes per theme.
- Return ONLY valid JSON — no markdown fences, no extra text.
"""


# ============================================================================
# Public API
# ============================================================================

def generate_report(project, user, report_type: str) -> tuple:
    """
    Generate an insight report for a project.

    Returns ``(InsightReport, error_string | None)``.
    On success ``error_string`` is ``None``.  On failure ``InsightReport`` may
    be ``None`` or a persisted report with ``status=failed``.
    """
    start_time = time.monotonic()
    logger.info("Insight report START — project=%s type=%s", project.id, report_type)

    config = REPORT_CONFIGS.get(report_type)
    if not config:
        return None, f"Unknown report type: {report_type}"

    # ── 1. Validate data availability ──────────────────────────────────────
    chunk_count = TranscriptChunk.objects.filter(
        interview__project=project,
        interview__is_deleted=False,
        is_deleted=False,
    ).count()

    if chunk_count == 0:
        return None, "No transcript data available. Upload and transcribe interviews first."

    # ── 2. Gather chunks ───────────────────────────────────────────────────
    try:
        if report_type == ReportType.FULL:
            # For summary-style full reports, ensure broad project coverage.
            relevant_chunks = _gather_balanced_project_chunks(project)
        else:
            relevant_chunks = _gather_relevant_chunks(project, config["seed_queries"])
    except Exception as exc:
        logger.error("Chunk gathering failed: %s", exc)
        return None, "Failed to gather transcript data for analysis."

    if not relevant_chunks:
        # Fall back to chronological sampling when embeddings are unavailable
        # or when balanced retrieval yielded no rows.
        relevant_chunks = _fallback_chronological_chunks(project)

    if not relevant_chunks:
        return None, "No processable transcript data found."

    if report_type != ReportType.FULL:
        # Keep thematic reports grounded in the full project by ensuring a
        # single interview cannot dominate the selected evidence.
        relevant_chunks = _balance_chunks_across_interviews(relevant_chunks)

    # ── 3. Aggregate statistics ────────────────────────────────────────────
    stats = _compute_chunk_statistics(project)

    # ── 4. Build LLM context (token-budgeted) ─────────────────────────────
    context, chunks_used = _build_report_context(
        relevant_chunks,
        interleave_by_interview=(report_type == ReportType.FULL),
    )

    # ── 5. Generate via LLM ───────────────────────────────────────────────
    report_content = _generate_with_llm(config["instruction"], context)
    if report_content is None:
        return None, "AI report generation failed after retries. Please try again."

    # Inject analysed chunk count from our pipeline (not the LLM's guess)
    report_content["total_chunks_analyzed"] = len(chunks_used)

    # ── 6. Persist report ─────────────────────────────────────────────────
    elapsed = round(time.monotonic() - start_time, 2)
    interview_ids = list({c["interview_id"] for c in chunks_used})

    report = InsightReport.objects.create(
        project=project,
        user=user,
        report_type=report_type,
        status=ReportStatus.COMPLETED,
        title=config["title"],
        content=report_content,
        metadata={
            "chunks_analyzed": len(chunks_used),
            "total_project_chunks": chunk_count,
            "interviews_included": len(interview_ids),
            "interview_ids": [str(i) for i in interview_ids],
            "generation_time_seconds": elapsed,
            "sentiment_distribution": stats,
        },
    )

    logger.info(
        "Insight report DONE — report=%s type=%s chunks=%d elapsed=%.2fs",
        report.id, report_type, len(chunks_used), elapsed,
    )
    return report, None


def get_project_reports(project, report_type=None):
    """Retrieve reports for a project, optionally filtered by type."""
    qs = InsightReport.objects.filter(project=project)
    if report_type:
        qs = qs.filter(report_type=report_type)
    return qs


def get_report_detail(report_id, project):
    """Retrieve a single report, or None."""
    try:
        return InsightReport.objects.get(id=report_id, project=project)
    except InsightReport.DoesNotExist:
        return None


def delete_report(report_id, project):
    """Soft-delete a report.  Returns True if found, False otherwise."""
    try:
        report = InsightReport.objects.get(id=report_id, project=project)
        report.soft_delete()
        return True
    except InsightReport.DoesNotExist:
        return False


# ============================================================================
# Internal: Semantic chunk gathering
# ============================================================================

def _gather_relevant_chunks(project, seed_queries: list[str]) -> list[dict]:
    """
    Use seed queries to find the most relevant transcript chunks via
    pgvector cosine similarity.  Deduplicates across seed queries.

    This avoids scanning ALL chunks — instead we do targeted vector
    searches for each seed query and merge the results.
    """
    from pgvector.django import CosineDistance

    seen_chunk_ids = set()
    results: list[dict] = []

    for seed in seed_queries:
        try:
            query_vector = generate_query_embedding(seed)
        except Exception as exc:
            logger.warning("Failed to embed seed query '%s': %s", seed[:60], exc)
            continue

        embeddings = (
            Embedding.objects.filter(
                transcript_chunk__interview__project=project,
                transcript_chunk__interview__is_deleted=False,
                transcript_chunk__is_deleted=False,
            )
            .annotate(distance=CosineDistance("vector", query_vector))
            .filter(distance__lt=INSIGHT_CLUSTER_THRESHOLD)
            .select_related("transcript_chunk", "transcript_chunk__interview")
            .order_by("distance")[: INSIGHT_CLUSTER_TOP_K]
        )

        for emb in embeddings:
            chunk = emb.transcript_chunk
            if chunk.id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.id)
            results.append({
                "chunk_id": str(chunk.id),
                "interview_id": str(chunk.interview_id),
                "interview_title": chunk.interview.title,
                "text": chunk.text,
                "start_time": chunk.start_time,
                "end_time": chunk.end_time,
                "speaker_label": chunk.speaker_label or "",
                "sentiment_score": chunk.sentiment_score,
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count or 0,
                "similarity": round(1 - emb.distance, 4),
            })

        if len(results) >= INSIGHT_MAX_CHUNKS:
            break

    # Sort by relevance (highest similarity first)
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:INSIGHT_MAX_CHUNKS]


def _fallback_chronological_chunks(project) -> list[dict]:
    """
    When no embeddings exist, fall back to a chronological sample of chunks.
    Uses database-level slicing — no full table scan.
    """
    chunks = (
        TranscriptChunk.objects.filter(
            interview__project=project,
            interview__is_deleted=False,
            is_deleted=False,
        )
        .select_related("interview")
        .order_by("interview", "chunk_index")[:INSIGHT_MAX_CHUNKS]
    )

    return [
        {
            "chunk_id": str(c.id),
            "interview_id": str(c.interview_id),
            "interview_title": c.interview.title,
            "text": c.text,
            "start_time": c.start_time,
            "end_time": c.end_time,
            "speaker_label": c.speaker_label or "",
            "sentiment_score": c.sentiment_score,
            "chunk_index": c.chunk_index,
            "token_count": c.token_count or 0,
            "similarity": None,
        }
        for c in chunks
    ]


def _balance_chunks_across_interviews(chunks: list[dict]) -> list[dict]:
    """
    Limit how many chunks any single interview can contribute.

    This preserves the most relevant evidence while preventing reports from
    becoming over-focused on the newest interview when it happens to match the
    seed queries strongly.
    """
    if not chunks:
        return []

    interview_ids = [c.get("interview_id") for c in chunks if c.get("interview_id")]
    unique_interview_count = len(set(interview_ids))
    if unique_interview_count <= 1:
        return chunks

    per_interview_cap = max(1, INSIGHT_MAX_CHUNKS // unique_interview_count)
    kept: list[dict] = []
    counts: dict[str, int] = defaultdict(int)

    for chunk in chunks:
        interview_id = chunk.get("interview_id")
        if not interview_id:
            kept.append(chunk)
            continue

        if counts[interview_id] >= per_interview_cap:
            continue

        kept.append(chunk)
        counts[interview_id] += 1

    return kept or chunks


def _gather_balanced_project_chunks(project) -> list[dict]:
    """
    Gather chunks for full summaries with broad interview coverage.

    Strategy:
    1. Split budget across interviews (round-robin by interview)
    2. Pull chronological chunks per interview up to per-interview cap
    3. Top up remaining budget chronologically across project
    """
    base_qs = (
        TranscriptChunk.objects.filter(
            interview__project=project,
            interview__is_deleted=False,
            is_deleted=False,
        )
        .select_related("interview")
        .order_by("interview_id", "chunk_index")
    )

    interview_ids = list(base_qs.values_list("interview_id", flat=True).distinct())
    if not interview_ids:
        return []

    per_interview_cap = max(1, INSIGHT_MAX_CHUNKS // len(interview_ids))
    selected_chunks: list[dict] = []
    selected_ids = set()

    for interview_id in interview_ids:
        interview_chunks = base_qs.filter(interview_id=interview_id)[:per_interview_cap]
        for chunk in interview_chunks:
            selected_ids.add(chunk.id)
            selected_chunks.append({
                "chunk_id": str(chunk.id),
                "interview_id": str(chunk.interview_id),
                "interview_title": chunk.interview.title,
                "text": chunk.text,
                "start_time": chunk.start_time,
                "end_time": chunk.end_time,
                "speaker_label": chunk.speaker_label or "",
                "sentiment_score": chunk.sentiment_score,
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count or 0,
                "similarity": None,
            })

        if len(selected_chunks) >= INSIGHT_MAX_CHUNKS:
            return selected_chunks[:INSIGHT_MAX_CHUNKS]

    remaining = INSIGHT_MAX_CHUNKS - len(selected_chunks)
    if remaining > 0:
        extra_chunks = base_qs.exclude(id__in=selected_ids)[:remaining]
        selected_chunks.extend([
            {
                "chunk_id": str(chunk.id),
                "interview_id": str(chunk.interview_id),
                "interview_title": chunk.interview.title,
                "text": chunk.text,
                "start_time": chunk.start_time,
                "end_time": chunk.end_time,
                "speaker_label": chunk.speaker_label or "",
                "sentiment_score": chunk.sentiment_score,
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count or 0,
                "similarity": None,
            }
            for chunk in extra_chunks
        ])

    return selected_chunks


# ============================================================================
# Internal: Statistics aggregation
# ============================================================================

def _compute_chunk_statistics(project) -> dict:
    """
    Aggregate sentiment distribution across all transcript chunks in the
    project.  Uses a single indexed query — no full table scan.
    """
    stats = (
        TranscriptChunk.objects.filter(
            interview__project=project,
            interview__is_deleted=False,
            is_deleted=False,
        )
        .exclude(sentiment_score__isnull=True)
        .aggregate(
            avg_sentiment=Avg("sentiment_score"),
            total_with_sentiment=Count("id"),
            positive_count=Count("id", filter=Q(sentiment_score__gt=0.1)),
            neutral_count=Count("id", filter=Q(sentiment_score__gte=-0.1, sentiment_score__lte=0.1)),
            negative_count=Count("id", filter=Q(sentiment_score__lt=-0.1)),
        )
    )

    total = stats["total_with_sentiment"] or 1  # avoid division by zero
    return {
        "average_sentiment": round(stats["avg_sentiment"] or 0, 4),
        "total_scored_chunks": stats["total_with_sentiment"],
        "positive_ratio": round((stats["positive_count"] or 0) / total, 4),
        "neutral_ratio": round((stats["neutral_count"] or 0) / total, 4),
        "negative_ratio": round((stats["negative_count"] or 0) / total, 4),
    }


# ============================================================================
# Internal: Context construction (token-budgeted)
# ============================================================================

def _build_report_context(
    chunks: list[dict],
    *,
    interleave_by_interview: bool = False,
) -> tuple[str, list[dict]]:
    """
    Build a context string from chunks while staying within the configured
    token budget.  Returns ``(context_string, list_of_included_chunks)``.
    """
    ordered_chunks = _interleave_chunks_by_interview(chunks) if interleave_by_interview else chunks
    unique_interview_count = len({c.get("interview_id") for c in chunks if c.get("interview_id")})
    full_report_token_cap = _compute_full_report_token_cap(unique_interview_count)

    parts: list[str] = []
    included: list[dict] = []
    included_interviews: set[str] = set()
    token_count = 0

    for c in ordered_chunks:
        raw_text = c.get("text", "")
        chunk_tokens = c.get("token_count", 0) or len(raw_text.split())
        text = raw_text

        # For full reports, trim long chunks so one interview cannot consume
        # most of the prompt budget.
        if interleave_by_interview and chunk_tokens > full_report_token_cap:
            text = _truncate_text_by_token_approx(raw_text, full_report_token_cap)
            chunk_tokens = full_report_token_cap

        if token_count + chunk_tokens > INSIGHT_MAX_CONTEXT_TOKENS and included:
            # If this interview has not been represented yet, force a very small
            # snippet so the final summary reflects broader project coverage.
            interview_id = c.get("interview_id")
            remaining = INSIGHT_MAX_CONTEXT_TOKENS - token_count
            if (
                interleave_by_interview
                and interview_id
                and interview_id not in included_interviews
                and remaining >= 40
            ):
                forced_tokens = min(60, remaining)
                text = _truncate_text_by_token_approx(raw_text, forced_tokens)
                chunk_tokens = forced_tokens
            else:
                break  # always include at least one chunk

        sentiment_str = (
            f", Sentiment: {c['sentiment_score']:.2f}"
            if c.get("sentiment_score") is not None
            else ""
        )
        speaker_str = f", Speaker: {c['speaker_label']}" if c.get("speaker_label") else ""
        start = c["start_time"] if c["start_time"] is not None else 0
        end = c["end_time"] if c["end_time"] is not None else 0

        part = (
            f"[Interview: {c['interview_title']}, "
            f"Time: {start:.1f}s–{end:.1f}s"
            f"{speaker_str}{sentiment_str}]\n"
            f"{text}"
        )
        parts.append(part)
        included_chunk = dict(c)
        included_chunk["text"] = text
        included_chunk["token_count"] = chunk_tokens
        included.append(included_chunk)
        if c.get("interview_id"):
            included_interviews.add(c["interview_id"])
        token_count += chunk_tokens

    return "\n\n---\n\n".join(parts), included


def _compute_full_report_token_cap(unique_interview_count: int) -> int:
    """Compute a per-interview token cap for full reports."""
    if unique_interview_count <= 0:
        return INSIGHT_FULL_PER_INTERVIEW_TOKEN_CAP

    dynamic_cap = INSIGHT_MAX_CONTEXT_TOKENS // unique_interview_count
    return max(80, min(INSIGHT_FULL_PER_INTERVIEW_TOKEN_CAP, dynamic_cap))


def _truncate_text_by_token_approx(text: str, token_cap: int) -> str:
    """Approximate token truncation using whitespace-separated words."""
    if token_cap <= 0 or not text:
        return ""

    words = text.split()
    if len(words) <= token_cap:
        return text

    return " ".join(words[:token_cap]) + " …"


def _interleave_chunks_by_interview(chunks: list[dict]) -> list[dict]:
    """Round-robin chunks across interviews to improve coverage in token-limited prompts."""
    by_interview: dict[str, list[dict]] = defaultdict(list)
    interview_order: list[str] = []

    for chunk in chunks:
        interview_id = chunk.get("interview_id", "")
        if interview_id not in by_interview:
            interview_order.append(interview_id)
        by_interview[interview_id].append(chunk)

    interleaved: list[dict] = []
    while True:
        progressed = False
        for interview_id in interview_order:
            items = by_interview.get(interview_id)
            if items:
                interleaved.append(items.pop(0))
                progressed = True
        if not progressed:
            break

    return interleaved


# ============================================================================
# Internal: LLM generation with retries
# ============================================================================

def _generate_with_llm(instruction: str, context: str) -> dict | None:
    """
    Send context to OpenAI and parse structured JSON response.
    Retries on transient API errors with exponential back-off.
    """
    client = _get_openai_client()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"{instruction}\n\nTranscript excerpts:\n\n{context}",
        },
    ]

    for attempt in range(1, INSIGHT_LLM_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=settings.OPENAI_CHAT_MODEL,
                messages=messages,
                temperature=INSIGHT_LLM_TEMPERATURE,
                max_tokens=INSIGHT_LLM_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            return _parse_llm_response(raw)

        except _RETRIABLE as exc:
            delay = INSIGHT_LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "Insight LLM transient error (attempt %d/%d), retrying in %.1fs: %s",
                attempt, INSIGHT_LLM_MAX_RETRIES, delay, exc,
            )
            if attempt < INSIGHT_LLM_MAX_RETRIES:
                time.sleep(delay)
            else:
                logger.error("Insight LLM exhausted all %d retries", INSIGHT_LLM_MAX_RETRIES)
                return None

        except json.JSONDecodeError as exc:
            logger.error("Insight LLM returned invalid JSON: %s", exc)
            return None

        except Exception as exc:
            logger.error("Insight LLM non-retriable error: %s", exc)
            return None

    return None  # pragma: no cover


def _parse_llm_response(raw: str) -> dict | None:
    """
    Parse the JSON response from the LLM.  Normalises structure to
    guarantee the expected shape regardless of LLM quirks.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Insight LLM returned non-JSON response")
        return None

    themes = data.get("themes", [])
    normalised_themes: list[dict] = []

    for idx, theme in enumerate(themes):
        if not isinstance(theme, dict):
            continue

        quotes = theme.get("supporting_quotes", [])
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

        normalised_themes.append({
            "rank": theme.get("rank", idx + 1),
            "theme": theme.get("theme", "Unnamed Theme"),
            "description": theme.get("description", ""),
            "frequency": theme.get("frequency", 0),
            "sentiment_avg": _clamp(theme.get("sentiment_avg", 0), -1.0, 1.0),
            "supporting_quotes": normalised_quotes,
        })

    return {
        "themes": normalised_themes,
        "summary": data.get("summary", ""),
        "total_chunks_analyzed": data.get("total_chunks_analyzed", 0),
        "methodology": data.get("methodology", ""),
    }


def _clamp(value, min_val, max_val):
    """Clamp a numeric value to [min_val, max_val]."""
    try:
        return max(min_val, min(float(value), max_val))
    except (TypeError, ValueError):
        return 0.0
