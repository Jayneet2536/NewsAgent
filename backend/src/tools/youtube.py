import logging
from datetime import datetime
from html import unescape

import requests

from ..config import settings
from ..models import NewsSource
from .time_window import in_window, parse_timestamp

logger = logging.getLogger(__name__)


class YouTubeFetcher:
    def __init__(self, api_key: str | None = None, transcript_client=None) -> None:
        self.api_key = api_key or settings.youtube_api_key
        self.transcript_client = transcript_client

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
                self.transcript_client = YouTubeTranscriptApi()
            except Exception:
                logger.warning("YouTube transcript client unavailable.", exc_info=True)
                return []

        sources = []
        seen = set()
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
            except Exception:
                logger.warning("YouTube search failed for query=%r duration=%s", query, duration)
                continue

            for candidate in candidates:
                video_id = candidate.get("id", {}).get("videoId")
                if not video_id or video_id in seen:
                    continue
                seen.add(video_id)
                try:
                    snippet = candidate["snippet"]
                    published_at = parse_timestamp(snippet.get("publishedAt"))
                    if published_at is None or not in_window(published_at, window_start, window_end):
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
                except Exception:
                    # Disabled captions, blocked requests, empty transcripts and bad metadata
                    # affect this candidate only; descriptions are never used as evidence.
                    logger.warning("Skipping YouTube video without usable transcript: %s", video_id)
        return sources
