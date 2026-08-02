"""APIRouter containing the /api/health and /api/research endpoints."""

import logging
from collections import defaultdict
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from ..graph.workflow import app as graph_app
from .schemas import (
    ArticleOut,
    ErrorResponse,
    ResearchRequest,
    ResearchResponse,
    SectionOut,
    StatsOut,
    VerificationOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    summary="Liveness check",
    response_description="Always returns {status: ok} — no API key dependencies.",
)
async def health_check() -> Dict[str, str]:
    """Trivial liveness probe; safe to call without any external credentials."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------


def _build_sections(articles: List[Dict[str, Any]]) -> List[SectionOut]:
    """Group flat article list by topic into SectionOut objects."""
    grouped: Dict[str, List[ArticleOut]] = defaultdict(list)
    for article in articles:
        topic = str(article.get("topic", "general"))
        grouped[topic].append(
            ArticleOut(
                title=str(article.get("title", "")),
                url=str(article.get("url", "")),
                snippet=str(article.get("snippet", "")),
            )
        )
    # Preserve insertion order (Python 3.7+ dicts are ordered)
    return [SectionOut(topic=topic, articles=arts) for topic, arts in grouped.items()]


@router.post(
    "/research",
    response_model=ResearchResponse,
    responses={
        422: {"description": "Query is empty or whitespace-only"},
        500: {"model": ErrorResponse, "description": "Graph run failed"},
    },
    summary="Run the full research pipeline",
    response_description=(
        "Structured JSON with interests, per-topic article sections, "
        "a markdown digest written by the LLM, verification score/issues, and stats."
    ),
)
async def run_research(request: ResearchRequest) -> ResearchResponse:
    """
    Submit a natural-language query to the planner→researcher→writer→verifier
    pipeline and receive structured JSON back.

    The pipeline may take **30–90 seconds** on a real run (multiple Tavily
    searches, HTTP article fetches, two LLM calls, and optional re-write
    retries).  This endpoint is synchronous; for very long queries consider
    adding a background-task + polling or SSE-streaming endpoint.
    """
    logger.info("POST /api/research query=%r", request.query)

    initial_state: Dict[str, Any] = {
        "interests": [request.query],
        "retry_count": 0,
    }

    try:
        final_state: Dict[str, Any] = graph_app.invoke(initial_state)
    except Exception as exc:
        # Log the real exception server-side; return a safe summary to the client.
        logger.exception("Graph run failed for query=%r", request.query)
        raise HTTPException(
            status_code=500,
            detail="Research pipeline failed. Check server logs for details.",
        ) from exc

    # --- Map AgentState fields to response schema ---
    articles: List[Dict[str, Any]] = final_state.get("articles") or []
    retry_count: int = final_state.get("retry_count", 0)
    # retry_count is incremented once per verifier pass, so retries = count - 1
    # (0 retries means one clean pass through writer→verifier).
    retries = max(0, retry_count - 1)

    response = ResearchResponse(
        interests=final_state.get("interests") or [],
        plan=final_state.get("plan") or "",
        sections=_build_sections(articles),
        digest_markdown=final_state.get("draft") or "",
        verification=VerificationOut(
            score=float(final_state.get("verification_score") or 0.0),
            issues=list(final_state.get("verification_issues") or []),
        ),
        stats=StatsOut(
            articles_fetched=len(articles),
            retries=retries,
        ),
    )

    logger.info(
        "POST /api/research completed interests=%s articles=%s score=%s retries=%s",
        response.interests,
        response.stats.articles_fetched,
        response.verification.score,
        response.stats.retries,
    )
    return response
