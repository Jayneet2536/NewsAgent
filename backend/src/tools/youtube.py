import logging
import re
from datetime import datetime
from html import unescape

import requests

from ..config import settings
from ..models import NewsSource
from .time_window import in_window, parse_timestamp

logger = logging.getLogger(__name__)


class TranscriptSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", 15)
        return super().request(method, url, **kwargs)


class YouTubeFetcher:
    def __init__(self, api_key: str | None = None, transcript_client=None) -> None:
        self.api_key = api_key or settings.youtube_api_key
        self.transcript_client = transcript_client
        self.seen_video_ids: set[str] = set()

    def fetch(
        self, query: str, topic: str, window_start: datetime,
        window_end: datetime, max_results: int = 3,
    ) -> list[NewsSource]:
        if not self.api_key:
            logger.warning("Skipping YouTube research: YOUTUBE_API_KEY is missing.")
            return []
        if self.transcript_client is None:
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                self.transcript_client = YouTubeTranscriptApi(http_client=TranscriptSession())
            except Exception as error:
                logger.warning("YouTube transcript client unavailable: %s", type(error).__name__)
                return []

        sources = []
        candidate_count = 0
        transcript_failures = 0
        logger.info("YouTube search query=%r window=%s..%s", query, window_start.isoformat(), window_end.isoformat())
        # Search both duration categories so interviews and long briefings qualify.
        for duration in ("medium", "long"):
            try:
                response = requests.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={
                        "key": self.api_key, "part": "snippet", "q": query,
                        "type": "video", "order": "date", "maxResults": max_results,
                        "publishedAfter": window_start.isoformat().replace("+00:00", "Z"),
                        "publishedBefore": window_end.isoformat().replace("+00:00", "Z"),
                        "videoDuration": duration,
                    },
                    timeout=15,
                )
                response.raise_for_status()
                candidates = response.json().get("items", [])
                candidate_count += len(candidates)
                logger.info("YouTube candidates query=%r duration=%s count=%s", query, duration, len(candidates))
            except Exception as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                reason = type(error).__name__
                try:
                    detail = error.response.json()["error"]["errors"][0]["reason"]
                    if isinstance(detail, str) and re.fullmatch(r"[a-zA-Z_]+", detail):
                        reason = detail
                except (AttributeError, KeyError, IndexError, TypeError, ValueError):
                    pass
                logger.warning("YouTube search failed query=%r duration=%s status=%s reason=%s",
                               query, duration, status, reason)
                continue

            for candidate in candidates:
                video_id = candidate.get("id", {}).get("videoId")
                if not video_id or video_id in self.seen_video_ids:
                    continue
                self.seen_video_ids.add(video_id)
                try:
                    snippet = candidate["snippet"]
                    published_at = parse_timestamp(snippet.get("publishedAt"))
                    if published_at is None or not in_window(published_at, window_start, window_end):
                        logger.info("YouTube video skipped for missing/out-of-window timestamp: %s", video_id)
                        continue
                    transcript = self.transcript_client.fetch(video_id)
                    content = " ".join(segment.text.strip() for segment in transcript if segment.text.strip())
                    thumbnails = snippet.get("thumbnails", {})
                    thumbnail = next((thumbnails[size]["url"] for size in ("high", "medium", "default") if size in thumbnails), None)
                    sources.append(NewsSource(
                        title=unescape(snippet.get("title", "")),
                        url=f"https://www.youtube.com/watch?v={video_id}",
                        source_type="youtube", content=unescape(content),
                        snippet=unescape(snippet.get("description", "")),
                        thumbnail_url=thumbnail, published_at=published_at,
                        topic=topic, publisher=snippet.get("channelTitle"),
                    ))
                    logger.info("YouTube transcript accepted video=%s characters=%s", video_id, len(content))
                except Exception as error:
                    # Disabled captions, blocked requests, empty transcripts and bad metadata
                    # affect this candidate only; descriptions are never used as evidence.
                    transcript_failures += 1
                    logger.warning("YouTube video skipped video=%s reason=%s", video_id, type(error).__name__)
        logger.info("YouTube query completed query=%r candidates=%s accepted=%s transcript_failures=%s",
                    query, candidate_count, len(sources), transcript_failures)
        return sources
