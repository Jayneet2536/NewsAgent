import logging
import re
import warnings
from typing import Optional

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from requests import RequestException

logger = logging.getLogger(__name__)


class ArticleFetcher:
    def __init__(self, timeout: int = 5, max_retries: int = 2) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "text/plain;q=0.8,*/*;q=0.7"
            ),
            "Accept-Language": "en-US,en;q=0.9",
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
                break
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
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
            tag.decompose()

        text = self._extract_from_article_containers(soup)
        if text:
            return text

        text = self._extract_from_paragraphs(soup)
        if text:
            return text

        return self._extract_from_metadata(soup)

    def _extract_from_article_containers(self, soup: BeautifulSoup) -> Optional[str]:
        selectors = [
            "article",
            "main",
            "[role='main']",
            ".article-content",
            ".post-content",
            ".entry-content",
            ".story-content",
            ".content",
        ]

        for selector in selectors:
            container = soup.select_one(selector)
            if not container:
                continue

            paragraphs = self._paragraph_text(container.find_all("p"))
            if paragraphs:
                return paragraphs

            text = self._clean_text(container.get_text(" ", strip=True))
            if len(text) >= 200:
                return text

        return None

    def _extract_from_paragraphs(self, soup: BeautifulSoup) -> Optional[str]:
        return self._paragraph_text(soup.find_all("p"))

    def _extract_from_metadata(self, soup: BeautifulSoup) -> Optional[str]:
        for selector in (
            "meta[property='og:description']",
            "meta[name='description']",
            "meta[name='twitter:description']",
        ):
            tag = soup.select_one(selector)
            if not tag:
                continue

            text = self._clean_text(tag.get("content", ""))
            if text:
                return text

        return None

    def _paragraph_text(self, paragraphs: list) -> Optional[str]:
        cleaned_paragraphs = [
            self._clean_text(paragraph.get_text(" ", strip=True))
            for paragraph in paragraphs
        ]
        useful_paragraphs = [
            paragraph for paragraph in cleaned_paragraphs if len(paragraph) >= 40
        ]
        text = "\n\n".join(useful_paragraphs)

        return text or None

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()


def fetch_article(url: str) -> Optional[str]:
    return ArticleFetcher().fetch(url)
