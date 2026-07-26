import logging
from typing import Dict, List

from tavily import TavilyClient

from ..config import settings

logger = logging.getLogger(__name__)


class TavilySearch:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.tavily_api_key
        if not self.api_key:
            raise ValueError("TAVILY_API_KEY is required to initialize TavilySearch.")

        self.client = TavilyClient(api_key=self.api_key)

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        logger.info("Searching Tavily for query=%r max_results=%s", query, max_results)

        try:
            response = self.client.search(query=query, max_results=max_results)
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
            }
            for result in results
        ]

        logger.info(
            "Tavily search completed for query=%r with %s results",
            query,
            len(formatted_results),
        )
        return formatted_results


def search_news(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    return TavilySearch().search(query=query, max_results=max_results)
