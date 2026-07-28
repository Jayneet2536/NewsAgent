import logging
import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from ..config import settings
from ..graph.state import AgentState
from ..tools.fetcher import ArticleFetcher
from ..tools.filter import RelevanceFilter
from ..tools.search import TavilySearch

logger = logging.getLogger(__name__)


def researcher_node(state: AgentState) -> Dict[str, Any]:
    """Search, fetch, and filter articles for the user's interests."""
    interests = state.get("interests", [])
    queries = _extract_search_queries(state.get("plan", ""), interests)

    if not queries:
        logger.warning("Researcher received no search queries.")
        return {"articles": []}

    try:
        search_client = TavilySearch(api_key=settings.tavily_api_key)
    except Exception as error:
        logger.error("Could not initialize Tavily search client: %s", error)
        return {"articles": []}

    fetcher = ArticleFetcher()
    relevance_filter = RelevanceFilter(use_llm=False)
    fetched_articles: List[Dict[str, Any]] = []

    for query in queries:
        logger.info("Researcher searching query=%r", query)
        try:
            search_results = search_client.search(query, max_results=3)
        except Exception as error:
            logger.error("Search failed for query=%r: %s", query, error)
            continue

        for result in search_results:
            url = result.get("url", "")
            if not url:
                logger.warning("Skipping search result without url query=%r", query)
                continue

            if _is_non_article_url(url):
                logger.info("Skipping non-article url=%r", url)
                continue

            logger.info("Researcher fetching url=%r", url)
            try:
                content = fetcher.fetch(url)
            except Exception as error:
                logger.error("Fetch failed for url=%r: %s", url, error)
                continue

            if not content:
                logger.warning("Skipping article with no fetched content url=%r", url)
                continue

            fetched_articles.append(
                {
                    "title": result.get("title", ""),
                    "url": url,
                    "content": content,
                    "snippet": result.get("snippet", ""),
                    "topic": _best_topic(query, interests),
                }
            )

    filtered_articles = _filter_by_interests(
        articles=fetched_articles,
        interests=interests,
        relevance_filter=relevance_filter,
    )
    logger.info("Researcher returning %s filtered articles", len(filtered_articles))
    return {"articles": filtered_articles}


def _extract_search_queries(plan: str, interests: List[str]) -> List[str]:
    """Extract likely search queries from a planner-generated text plan."""
    queries = []

    for line in plan.splitlines():
        cleaned_line = line.strip()
        if not cleaned_line:
            continue

        quoted_queries = re.findall(r'"([^"]+)"', cleaned_line)
        if quoted_queries:
            queries.extend(quoted_queries)
            continue

        query = re.sub(r"^[-*\d.\s]+", "", cleaned_line)
        query = re.sub(r"^search\s+for\s+", "", query, flags=re.IGNORECASE)
        query = query.strip()
        if query:
            queries.append(query)

    if not queries:
        queries = [f"latest {interest} news last 7 days" for interest in interests]

    return _deduplicate(queries)


def _filter_by_interests(
    articles: List[Dict[str, Any]],
    interests: List[str],
    relevance_filter: RelevanceFilter,
) -> List[Dict[str, Any]]:
    """Filter fetched articles for each interest and aggregate the results."""
    if not interests:
        return [_article_output(article) for article in articles]

    filtered_articles: List[Dict[str, Any]] = []
    seen_urls = set()

    for interest in interests:
        relevant_articles = relevance_filter.filter_articles(articles, interest)
        for article in relevant_articles:
            url = article.get("url", "")
            if url in seen_urls:
                continue

            seen_urls.add(url)
            filtered_articles.append(_article_output({**article, "topic": interest}))

    return filtered_articles


def _article_output(article: Dict[str, Any]) -> Dict[str, str]:
    """Return the article fields expected by AgentState."""
    return {
        "title": str(article.get("title", "")),
        "url": str(article.get("url", "")),
        "content": str(article.get("content", "")),
        "snippet": str(article.get("snippet", "")),
        "topic": str(article.get("topic", "")),
    }


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
    path = parsed_url.path.lower().rstrip("/")

    if path.endswith(("/feed", ".xml", ".rss", "/rss")):
        return True

    listing_segments = {"/tag/", "/tags/", "/category/", "/author/", "/search/"}
    return any(segment in path for segment in listing_segments)
