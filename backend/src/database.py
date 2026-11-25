"""Durable storage for completed pipeline runs, including their original evidence."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .errors import PipelineError


_COLUMNS = """
    stored_at TEXT NOT NULL,
    digest_markdown TEXT NOT NULL,
    interests_json TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    verification_json TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    window_start TEXT,
    window_end TEXT
"""
_INSERT = """
    INSERT INTO news_feeds
    (stored_at, digest_markdown, interests_json, sources_json,
     verification_json, plan_json, window_start, window_end)
    VALUES ({placeholders})
"""


def persist_feed_node(state: dict) -> dict:
    digest = state.get("draft", "").strip()
    if not digest:
        raise PipelineError("There is no completed digest to save.")
    stored_at = datetime.now(timezone.utc).isoformat()
    record = (
        stored_at, digest, json.dumps(state.get("interests", [])),
        json.dumps(state.get("sources", state.get("articles", []))),
        json.dumps({"score": state.get("verification_score", 0),
                    "issues": state.get("verification_issues", [])}),
        state.get("plan", "{}"), state.get("window_start"), state.get("window_end"),
    )
    try:
        if settings.database_url:
            feed_id = _save_postgres(record)
        else:
            feed_id = _save_sqlite(record)
    except PipelineError:
        raise
    except Exception as error:
        # Never fall back to ephemeral SQLite when cloud persistence fails.
        raise PipelineError("The feed could not be saved. Check database configuration and connectivity.") from error
    return {"final_digest": digest, "feed_id": feed_id, "stored_at": stored_at}


def _save_sqlite(record: tuple) -> int:
    path = Path(settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(f"CREATE TABLE IF NOT EXISTS news_feeds (id INTEGER PRIMARY KEY AUTOINCREMENT, {_COLUMNS})")
        cursor = connection.execute(_INSERT.format(placeholders=", ".join(["?"] * 8)), record)
        return cursor.lastrowid


def _save_postgres(record: tuple) -> int:
    if not settings.database_url.startswith(("postgresql://", "postgres://")):
        raise PipelineError("DATABASE_URL must be a PostgreSQL connection URL.")
    import psycopg

    with psycopg.connect(settings.database_url, connect_timeout=10) as connection:
        connection.execute(f"CREATE TABLE IF NOT EXISTS news_feeds (id BIGSERIAL PRIMARY KEY, {_COLUMNS})")
        cursor = connection.execute(_INSERT.format(placeholders=", ".join(["%s"] * 8)) + " RETURNING id", record)
        return cursor.fetchone()[0]
