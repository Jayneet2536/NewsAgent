import logging
import re
from typing import Any, Dict, List, Optional

from ..config import settings

logger = logging.getLogger(__name__)


class RelevanceFilter:
    def __init__(self, threshold: float = 0.3, max_results: int = 5) -> None:
        self.threshold = threshold
        self.max_results = max_results
        self._llm_client: Optional[Any] = None

    def score_relevance(self, interest: str, article_text: str) -> float:
        keyword_score = self._keyword_relevance_score(interest, article_text)
        llm_score = self._llm_relevance_score(interest, article_text)

        if llm_score is None:
            return keyword_score

        return min(max((keyword_score * 0.4) + (llm_score * 0.6), 0.0), 1.0)

    def filter_articles(
        self,
        articles: List[Dict[str, Any]],
        interest: str,
    ) -> List[Dict[str, Any]]:
        scored_articles = []

        for article in articles:
            article_text = self._article_text(article)
            score = self.score_relevance(interest, article_text)
            logger.info(
                "Article relevance score=%s interest=%r url=%r",
                score,
                interest,
                article.get("url", ""),
            )

            if score >= self.threshold:
                scored_article = {**article, "relevance_score": score}
                scored_articles.append(scored_article)

        scored_articles.sort(key=lambda item: item["relevance_score"], reverse=True)
        return scored_articles[: self.max_results]

    def _keyword_relevance_score(self, interest: str, article_text: str) -> float:
        interest_keywords = self._keywords(interest)
        article_keywords = set(self._keywords(article_text))

        if not interest_keywords or not article_keywords:
            return 0.0

        matches = sum(1 for keyword in interest_keywords if keyword in article_keywords)
        return min(matches / len(interest_keywords), 1.0)

    def _llm_relevance_score(self, interest: str, article_text: str) -> Optional[float]:
        client = self._get_llm_client()
        if client is None:
            return None

        prompt = (
            "Rate how relevant this article is to the user interest on a scale from "
            "0 to 1. Return only a decimal number.\n\n"
            f"Interest: {interest}\n\n"
            f"Article:\n{article_text[:4000]}"
        )

        try:
            response = client.models.generate_content(
                model=settings.model_name,
                contents=prompt,
            )
            text = getattr(response, "text", "")
            return self._parse_score(text)
        except Exception as error:
            logger.warning("LLM relevance check failed: %s", error)
            return None

    def _get_llm_client(self) -> Optional[Any]:
        if not settings.gemini_api_key:
            logger.warning("Skipping LLM relevance check because GEMINI_API_KEY is missing.")
            return None

        if self._llm_client is not None:
            return self._llm_client

        try:
            from google import genai
        except ImportError:
            logger.warning("Skipping LLM relevance check because google-genai is missing.")
            return None

        self._llm_client = genai.Client(api_key=settings.gemini_api_key)
        return self._llm_client

    def _article_text(self, article: Dict[str, Any]) -> str:
        return " ".join(
            str(article.get(field, ""))
            for field in ("title", "topic", "snippet", "content")
            if article.get(field)
        )

    def _keywords(self, text: str) -> List[str]:
        return [
            keyword
            for keyword in re.findall(r"[a-zA-Z0-9]+", text.lower())
            if len(keyword) > 2
        ]

    def _parse_score(self, text: str) -> Optional[float]:
        match = re.search(r"0(?:\.\d+)?|1(?:\.0+)?", text)
        if not match:
            return None

        return min(max(float(match.group()), 0.0), 1.0)


def filter_articles(
    articles: List[Dict[str, Any]],
    interest: str,
    threshold: float = 0.3,
) -> List[Dict[str, Any]]:
    return RelevanceFilter(threshold=threshold).filter_articles(articles, interest)
