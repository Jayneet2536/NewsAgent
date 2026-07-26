import logging
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup
from requests import RequestException

logger = logging.getLogger(__name__)


class ArticleFetcher:
    def __init__(self, timeout: int = 5, max_retries: int = 2) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; NewsAgent/0.1; "
                "+https://example.com/newsagent)"
            )
        }

    def fetch(self, url: str) -> Optional[str]:
        for attempt in range(1, self.max_retries + 2):
            try:
                logger.info("Fetching article url=%r attempt=%s", url, attempt)
                response = requests.get(
                    url,
                    headers=self.headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()

                text = self._extract_text(response.text)
                if text:
                    logger.info("Fetched article url=%r length=%s", url, len(text))
                    return text

                logger.warning("No article text found url=%r attempt=%s", url, attempt)
            except RequestException as error:
                logger.warning(
                    "Article fetch failed url=%r attempt=%s error=%s",
                    url,
                    attempt,
                    error,
                )
            except Exception:
                logger.exception("Unexpected article fetch error url=%r", url)
                return None

        logger.error("Article fetch exhausted retries url=%r", url)
        return None

    def _extract_text(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        paragraphs = [
            self._clean_text(paragraph.get_text(" ", strip=True))
            for paragraph in soup.find_all("p")
        ]
        text = "\n\n".join(paragraph for paragraph in paragraphs if paragraph)

        return text or None

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()


def fetch_article(url: str) -> Optional[str]:
    return ArticleFetcher().fetch(url)
