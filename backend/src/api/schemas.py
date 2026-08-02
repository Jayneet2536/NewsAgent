"""Pydantic request/response schemas for the NewsAgent REST API."""

from typing import List

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class ResearchRequest(BaseModel):
    """Body accepted by POST /api/research."""

    query: str

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be empty or whitespace-only")
        return stripped


# ---------------------------------------------------------------------------
# Response sub-models
# ---------------------------------------------------------------------------


class ArticleOut(BaseModel):
    """A single article as returned to the frontend.

    ``content`` is intentionally omitted — it can be tens of kilobytes of raw
    HTML/text and the frontend doesn't need it; ``snippet`` (100-200 chars) is
    sufficient for display.
    """

    title: str
    url: str
    snippet: str


class SectionOut(BaseModel):
    """Articles grouped by research topic."""

    topic: str
    articles: List[ArticleOut]


class VerificationOut(BaseModel):
    """Output from the verifier node."""

    score: float
    issues: List[str]


class StatsOut(BaseModel):
    """Lightweight run statistics."""

    articles_fetched: int
    retries: int


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------


class ResearchResponse(BaseModel):
    """Full response returned by POST /api/research.

    ``digest_markdown`` carries the writer node's output verbatim.  The writer
    produces a single unified Markdown document (not per-topic snippets), so
    exposing it as a labelled markdown field is more honest than trying to
    parse/split it.  Frontends can render it with any Markdown library.

    ``sections`` contains the structured article data grouped by topic, derived
    directly from the researcher node's output — no LLM post-processing.
    """

    interests: List[str]
    plan: str
    sections: List[SectionOut]
    digest_markdown: str
    verification: VerificationOut
    stats: StatsOut


# ---------------------------------------------------------------------------
# Error response
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """JSON body returned on 500 errors.

    ``detail`` is a safe, non-leaking summary.  The real exception is always
    logged server-side via the standard ``logging`` module.
    """

    detail: str
