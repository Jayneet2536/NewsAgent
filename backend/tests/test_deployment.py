import json
import os
from pathlib import Path
import shutil
import subprocess
from unittest.mock import MagicMock

import pytest

from src.config import settings
from src.database import persist_feed_node
from src.errors import PipelineError


def test_postgres_saves_feed_and_timestamp_without_touching_sqlite(monkeypatch):
    connection = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (42,)
    connection.execute.return_value = cursor
    connect = MagicMock()
    connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr("psycopg.connect", connect)
    local_save = MagicMock()
    monkeypatch.setattr("src.database._save_sqlite", local_save)
    monkeypatch.setattr(settings, "database_url", "postgresql://test:secret@db.example/news?sslmode=require")
    sources = [{"url": "https://www.youtube.com/watch?v=abc", "content": "Original transcript"}]
    result = persist_feed_node({"draft": "A news digest", "sources": sources,
                                "verification_score": 95, "plan": "{}"})
    assert result["feed_id"] == 42
    assert result["stored_at"].endswith("+00:00")
    assert connection.execute.call_count == 2
    sql, record = connection.execute.call_args.args
    assert "RETURNING id" in sql and "%s" in sql
    assert record[0] == result["stored_at"]
    assert record[1] == result["final_digest"]
    assert json.loads(record[3]) == sources
    local_save.assert_not_called()
    connect.assert_called_once_with(settings.database_url, connect_timeout=10)
    connect.return_value.__exit__.assert_called_once()


def test_postgres_failure_does_not_fall_back_to_ephemeral_disk(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql://test:secret@db.example/news")
    monkeypatch.setattr("psycopg.connect", MagicMock(side_effect=OSError("unreachable")))
    local_save = MagicMock()
    monkeypatch.setattr("src.database._save_sqlite", local_save)
    with pytest.raises(PipelineError, match="could not be saved"):
        persist_feed_node({"draft": "A news digest"})
    local_save.assert_not_called()


def test_invalid_database_url_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "https://not-a-database.example")
    connect = MagicMock()
    monkeypatch.setattr("psycopg.connect", connect)
    with pytest.raises(PipelineError, match="PostgreSQL connection URL"):
        persist_feed_node({"draft": "A news digest"})
    connect.assert_not_called()


@pytest.fixture
def frontend_build(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to check the static-site build")
    source = Path(__file__).resolve().parents[2] / "frontend"
    for name in ("index.html", "build.mjs"):
        shutil.copyfile(source / name, tmp_path / name)
    return tmp_path


def test_static_build_uses_public_backend_origin_and_excludes_secrets(frontend_build):
    environment = {**os.environ, "PUBLIC_API_BASE": "https://newsagent-api.onrender.com/",
                   "GROQ_API_KEY": "DO_NOT_EXPOSE", "DATABASE_URL": "DO_NOT_EXPOSE"}
    subprocess.run(["node", str(frontend_build / "build.mjs")], check=True, capture_output=True,
                   text=True, env=environment)
    config = (frontend_build / "dist/config.js").read_text(encoding="utf-8")
    assert '"apiBase":"https://newsagent-api.onrender.com"' in config
    assert "DO_NOT_EXPOSE" not in config
    subprocess.run(["node", "--check", str(frontend_build / "dist/config.js")],
                   check=True, capture_output=True, text=True)
    html = (frontend_build / "dist/index.html").read_text(encoding="utf-8")
    assert 'src="config.js"' in html
    assert "NEWSAGENT_CONFIG?.apiBase" in html


def test_static_build_preserves_same_origin_when_unconfigured(frontend_build):
    environment = {**os.environ, "PUBLIC_API_BASE": ""}
    subprocess.run(["node", str(frontend_build / "build.mjs")], check=True, capture_output=True,
                   text=True, env=environment)
    assert '"apiBase":""' in (frontend_build / "dist/config.js").read_text(encoding="utf-8")


@pytest.mark.parametrize("base", ["javascript:alert(1)", "https://example.com/api",
                                  "https://user:password@example.com", "http://public.example.com"])
def test_static_build_rejects_unsafe_or_incorrect_api_origins(frontend_build, base):
    result = subprocess.run(["node", str(frontend_build / "build.mjs")], capture_output=True,
                            text=True, env={**os.environ, "PUBLIC_API_BASE": base})
    assert result.returncode != 0
    assert not (frontend_build / "dist/config.js").exists()
