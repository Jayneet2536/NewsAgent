

from typing import List

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class ResearchRequest(BaseModel):
    

    query: str

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be empty or whitespace-only")
        return stripped





class ArticleOut(BaseModel):
    

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




class ResearchResponse(BaseModel):
    

    interests: List[str]
    plan: str
    sections: List[SectionOut]
    digest_markdown: str
    verification: VerificationOut
    stats: StatsOut




class ErrorResponse(BaseModel):
    detail: str
    

