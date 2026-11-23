from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator


class SearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    web_queries: list[str]
    youtube_queries: list[str]

    @field_validator("web_queries", "youtube_queries")
    @classmethod
    def validate_queries(cls, queries: list[str]) -> list[str]:
        if not queries or any(not query.strip() for query in queries):
            raise ValueError("Queries must be nonempty strings in a nonempty list.")
        return list(dict.fromkeys(query.strip() for query in queries))


class NewsSource(BaseModel):
    title: str
    url: HttpUrl
    source_type: Literal["article", "youtube"]
    content: str
    snippet: str | None = None
    thumbnail_url: HttpUrl | None = None
    published_at: datetime | None = None
    topic: str
    publisher: str | None = None

    @field_validator("content")
    @classmethod
    def usable_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Source content must not be blank.")
        return value.strip()

    @field_validator("published_at")
    @classmethod
    def utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None or value.tzinfo is None:
            return None
        return value.astimezone(timezone.utc)
