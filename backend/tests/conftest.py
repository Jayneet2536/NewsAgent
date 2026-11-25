import pytest

from src.config import settings


@pytest.fixture(autouse=True)
def isolate_database(monkeypatch):
    """Tests must never connect to a database configured in the user's .env."""
    monkeypatch.setattr(settings, "database_url", "")
