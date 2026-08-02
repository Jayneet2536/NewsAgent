"""Tests for the NewsAgent REST API.

Run with:
    cd backend
    python -m pytest tests/test_api.py -v

All three tests monkeypatch the compiled LangGraph ``app`` object so no real
API keys, network calls, or LLM usage are required.
"""

import json
import traceback
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# A minimal AgentState-shaped dict that matches what the real graph returns.
_MOCK_FINAL_STATE: Dict[str, Any] = {
    "interests": ["AI research", "climate tech"],
    "plan": '- Search for "latest AI research news"\n- Search for "climate tech updates"',
    "articles": [
        {
            "title": "Breakthrough in LLM Efficiency",
            "url": "https://example.com/ai-article",
            "content": "Long raw article content...",
            "snippet": "Researchers unveiled a new approach to LLM training.",
            "topic": "AI research",
        },
        {
            "title": "Solar Panel Costs Hit Record Low",
            "url": "https://example.com/climate-article",
            "content": "Long raw article content...",
            "snippet": "The cost of solar panels dropped by 40% this quarter.",
            "topic": "climate tech",
        },
    ],
    "draft": "## AI Research\n\nResearchers unveiled...\n\n## Climate Tech\n\nSolar costs dropped...",
    "verification_score": 88.0,
    "verification_issues": [],
    "retry_count": 1,
    "final_digest": "",
}


# ---------------------------------------------------------------------------
# Test 1 — Happy path
# ---------------------------------------------------------------------------


def test_research_endpoint_returns_200_with_expected_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the graph and assert the full response shape and key values."""

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = _MOCK_FINAL_STATE

    monkeypatch.setattr("src.api.router.graph_app", mock_graph)

    response = client.post("/api/research", json={"query": "AI research and climate tech"})

    assert response.status_code == 200, response.text
    body = response.json()

    # Top-level keys
    assert "interests" in body
    assert "plan" in body
    assert "sections" in body
    assert "digest_markdown" in body
    assert "verification" in body
    assert "stats" in body

    # interests
    assert isinstance(body["interests"], list)
    assert len(body["interests"]) > 0

    # sections structure
    sections = body["sections"]
    assert isinstance(sections, list)
    assert len(sections) == 2  # one per topic
    for section in sections:
        assert "topic" in section
        assert "articles" in section
        for article in section["articles"]:
            assert "title" in article
            assert "url" in article
            assert "snippet" in article
            # content must NOT be leaked to the client (it's large raw HTML)
            assert "content" not in article

    # digest_markdown
    assert isinstance(body["digest_markdown"], str)
    assert len(body["digest_markdown"]) > 0

    # verification
    verification = body["verification"]
    assert "score" in verification
    assert isinstance(verification["score"], float)
    assert "issues" in verification
    assert isinstance(verification["issues"], list)

    # stats
    stats = body["stats"]
    assert stats["articles_fetched"] == 2
    assert isinstance(stats["retries"], int)

    # Confirm the graph was called with the correct initial state
    mock_graph.invoke.assert_called_once_with(
        {"interests": ["AI research and climate tech"], "retry_count": 0}
    )


# ---------------------------------------------------------------------------
# Test 2 — 422 on empty / whitespace-only query
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_query", ["", "   ", "\t\n"])
def test_research_endpoint_returns_422_on_blank_query(bad_query: str) -> None:
    """FastAPI + Pydantic validation must reject empty/whitespace queries."""
    response = client.post("/api/research", json={"query": bad_query})
    assert response.status_code == 422, response.text
    body = response.json()
    # FastAPI validation errors always include a "detail" key
    assert "detail" in body


# ---------------------------------------------------------------------------
# Test 3 — 500 on graph failure, with no raw traceback in response body
# ---------------------------------------------------------------------------


def test_research_endpoint_returns_500_without_traceback_on_graph_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the graph raises, the client must get a clean JSON error, not a stack trace."""

    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = RuntimeError("Tavily API quota exceeded")

    monkeypatch.setattr("src.api.router.graph_app", mock_graph)

    response = client.post("/api/research", json={"query": "some valid query"})

    assert response.status_code == 500, response.text

    # Response must be valid JSON
    try:
        body = response.json()
    except json.JSONDecodeError:
        pytest.fail("500 response body is not valid JSON")

    # Must have a detail field
    assert "detail" in body

    # The detail string must NOT contain Python traceback markers
    detail_str = str(body["detail"])
    assert "Traceback" not in detail_str
    assert "RuntimeError" not in detail_str
    assert "Tavily API quota exceeded" not in detail_str


# ---------------------------------------------------------------------------
# Test 4 — Health check
# ---------------------------------------------------------------------------


def test_health_check_returns_200() -> None:
    """GET /api/health must always return 200 with {status: ok}."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
