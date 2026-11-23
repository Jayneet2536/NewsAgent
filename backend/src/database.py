"""Durable storage for completed pipeline runs, including their original evidence."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import settings


def persist_feed_node(state: dict) -> dict:
    path = Path(settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = state.get("draft", "")
    with sqlite3.connect(path) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS news_feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stored_at TEXT NOT NULL,
                digest_markdown TEXT NOT NULL,
                interests_json TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                verification_json TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                window_start TEXT,
                window_end TEXT
            )
        """)
        stored_at = datetime.now(timezone.utc).isoformat()
        cursor = connection.execute("""
            INSERT INTO news_feeds
            (stored_at, digest_markdown, interests_json, sources_json,
             verification_json, plan_json, window_start, window_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stored_at, digest, json.dumps(state.get("interests", [])),
            json.dumps(state.get("sources", state.get("articles", []))),
            json.dumps({"score": state.get("verification_score", 0),
                        "issues": state.get("verification_issues", [])}),
            state.get("plan", "{}"), state.get("window_start"), state.get("window_end"),
        ))
        feed_id = cursor.lastrowid
    return {"final_digest": digest, "feed_id": feed_id, "stored_at": stored_at}
