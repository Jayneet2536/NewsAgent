import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib.parse import urlparse, urlsplit, urlunsplit

from ..config import settings
from ..graph.state import AgentState
from ..models import NewsSource, SearchPlan
from ..tools.fetcher import ArticleFetcher
from ..tools.filter import RelevanceFilter
from ..tools.search import TavilySearch
from ..tools.youtube import YouTubeFetcher
from ..tools.time_window import in_window, parse_timestamp

logger = logging.getLogger(__name__)


def researcher_node(state: AgentState) -> Dict[str, Any]:
    interests = state.get("interests", [])
    plan = SearchPlan.model_validate({
        "web_queries": state.get("web_queries") or [f"{topic} news" for topic in interests] or ["general news"],
        "youtube_queries": state.get("youtube_queries") or [f"{topic} news briefing" for topic in interests] or ["general news briefing"],
    })
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24)
    collected = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [
            pool.submit(_fetch_articles, plan.web_queries, interests, start, end),
            pool.submit(_fetch_videos, plan.youtube_queries, interests, start, end),
        ]
        for job in jobs:
            try:
                collected.extend(job.result())
            except Exception:
                logger.exception("Research provider failed; retaining other provider's results.")

    sources = []
    seen = set()
    relevance = RelevanceFilter(use_llm=False)
    for item in collected:
        try:
            source = NewsSource.model_validate(item)
        except ValueError:
            logger.warning("Skipping invalid research source.")
            continue
        if not in_window(source.published_at, start, end):
            continue
        parts = urlsplit(str(source.url))
        canonical = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))
        if canonical in seen:
            continue
        # Score evidence itself, excluding the assigned topic, which would create false matches.
        text = f"{source.title} {source.snippet or ''} {source.content}"
        matches = [(relevance.score_relevance(interest, text), interest) for interest in interests]
        if matches:
            score, topic = max(matches, key=lambda match: match[0])
            if score < relevance.threshold:
                continue
            source.topic = topic
        seen.add(canonical)
        sources.append(source.model_dump(mode="json"))
    return {"sources": sources, "articles": sources,
            "window_start": start.isoformat(), "window_end": end.isoformat()}


def _fetch_articles(queries, interests, start, end) -> list[NewsSource]:
    search = TavilySearch(api_key=settings.tavily_api_key)
    fetcher = ArticleFetcher()
    sources = []
    seen = set()
    for query in queries:
        try:
            results = search.search(query, max_results=3, days=1, topic="news",
                                    window_start=start, window_end=end)
        except Exception:
            logger.exception("Tavily query failed: %r", query)
            continue
        for result in results:
            url = result.get("url", "")
            if not url or url in seen or _is_non_article_url(url):
                continue
            seen.add(url)
            published_at = parse_timestamp(result.get("published_at"))
            if not in_window(published_at, start, end):
                continue
            try:
                content = fetcher.fetch(url)
                if not content:
                    continue
                sources.append(NewsSource(
                    title=result.get("title", ""), url=url, source_type="article",
                    content=content, snippet=result.get("snippet"),
                    published_at=published_at, publisher=result.get("publisher"),
                    topic=_best_topic(query, interests),
                ))
            except Exception:
                logger.warning("Skipping article that could not be fetched: %s", url)
    return sources


def _fetch_videos(queries, interests, start, end) -> list[NewsSource]:
    fetcher = YouTubeFetcher()
    sources = []
    for query in queries:
        try:
            sources.extend(fetcher.fetch(query, _best_topic(query, interests), start, end))
        except Exception:
            logger.exception("YouTube query failed: %r", query)
    return sources


def _best_topic(query: str, interests: List[str]) -> str:
    """Choose the closest user interest for a query."""
    query_lower = query.lower()
    for interest in interests:
        if interest.lower() in query_lower:
            return interest

    return interests[0] if interests else query


def _deduplicate(items: List[str]) -> List[str]:
    """Remove duplicate strings while preserving order."""
    seen = set()
    deduplicated = []

    for item in items:
        normalized = item.lower()
        if normalized in seen:
            continue

        seen.add(normalized)
        deduplicated.append(item)

    return deduplicated


def _is_non_article_url(url: str) -> bool:
    """Identify URLs that are usually feeds or listing pages, not articles."""
    parsed_url = urlparse(url)

    # Reject anything that isn't a real absolute http(s) URL — catches the
    # relative "/goto?url=..." redirect fragments some search results return.
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        return True

    path = parsed_url.path.lower().rstrip("/")

    if path.endswith(("/feed", ".xml", ".rss", "/rss")):
        return True

    listing_segments = {"/tag/", "/tags/", "/category/", "/author/", "/search/"}
    return any(segment in path for segment in listing_segments)