from typing import Dict, List, TypedDict


class Article(TypedDict):
    title: str
    url: str
    content: str
    snippet: str
    topic: str


class AgentState(TypedDict):
    interests: List[str]
    plan: str
    web_queries: List[str]
    youtube_queries: List[str]
    sources: List[Dict]
    window_start: str
    window_end: str
    feed_id: int
    stored_at: str
    articles: List[Dict]
    draft_batches: List[Dict]
    draft: str
    verification_score: float
    verification_issues: List[str]
    retry_count: int
    final_digest: str


GraphState = AgentState
