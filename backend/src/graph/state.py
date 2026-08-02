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
    articles: List[Dict]
    draft: str
    verification_score: float
    verification_issues: List[str]
    retry_count: int
    final_digest: str


GraphState = AgentState
