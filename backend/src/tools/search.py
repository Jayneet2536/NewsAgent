import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from .time_window import in_window, parse_timestamp

from tavily import TavilyClient

from ..config import settings

logger = logging.getLogger(__name__)


class TavilySearch:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.tavily_api_key
        if not self.api_key:
            raise ValueError("TAVILY_API_KEY is required to initialize TavilySearch.")

        self.client = TavilyClient(api_key=self.api_key)

    def search(
        self,
        query: str,
        max_results: int = 5,
        days: Optional[int] = 1,
        topic: str = "news",
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> List[Dict[str, Any]]:
        """Search Tavily, scoped to recent news by default.

        `topic="news"` + `days=N` ask Tavily itself to restrict to the last
        N days, instead of relying on the query text (e.g. "past 7 days")
        to hint at recency, which search engines don't reliably honor.
        """
        logger.info(
            "Searching Tavily for query=%r max_results=%s days=%s topic=%r",
            query,
            max_results,
            days,
            topic,
        )

        search_kwargs = {
            "query": query,
            "max_results": max_results,
            "topic": topic,
        }
        # Tavily only accepts `days` when topic="news"; guard against misuse.
        if topic == "news" and days is not None:
            search_kwargs["days"] = days

        try:
            response = self.client.search(**search_kwargs)
        except Exception as error:
            message = str(error).lower()
            if "rate" in message or "429" in message:
                logger.warning("Tavily rate limit hit for query=%r: %s", query, error)
                return []

            logger.exception("Tavily search failed for query=%r", query)
            return []

        results = response.get("results", [])
        formatted_results = [
            {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "snippet": result.get("content", ""),
                "published_at": parse_timestamp(result.get("published_date")),
                "publisher": result.get("source"),
            }
            for result in results
            if window_start is None or window_end is None
            or in_window(parse_timestamp(result.get("published_date")), window_start, window_end)
        ]

        logger.info(
            "Tavily search completed for query=%r with %s results",
            query,
            len(formatted_results),
        )
        return formatted_results


def search_news(query: str, max_results: int = 5, days: int = 1) -> List[Dict[str, Any]]:
    return TavilySearch().search(query=query, max_results=max_results, days=days)