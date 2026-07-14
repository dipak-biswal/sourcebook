"""DuckDuckGo web search helper."""

from unittest.mock import MagicMock, patch

from app.agents.web_search import normalize_web_search_query, search_web


def test_search_web_requires_query():
    out = search_web("  ")
    assert out["result_count"] == 0
    assert out["error"] == "Query is required"


def test_normalize_web_search_query_replaces_stale_year():
    normalized, original = normalize_web_search_query(
        "senior full-stack AI developer skills requirements 2023",
        current_year=2026,
    )
    assert original == "senior full-stack AI developer skills requirements 2023"
    assert normalized == "senior full-stack AI developer skills requirements 2026"


def test_normalize_web_search_query_appends_current_year():
    normalized, original = normalize_web_search_query(
        "senior full stack AI engineer requirements",
        current_year=2026,
    )
    assert original == "senior full stack AI engineer requirements"
    assert normalized == "senior full stack AI engineer requirements 2026"


def test_normalize_web_search_query_leaves_historical_queries():
    normalized, original = normalize_web_search_query(
        "Python 3.10 release notes 2020",
        current_year=2026,
    )
    assert original is None
    assert normalized == "Python 3.10 release notes 2020"


@patch("app.agents.web_search.DDGS")
def test_search_web_normalizes_results(mock_ddgs_cls):
    mock_ddgs_cls.return_value.text.return_value = [
        {
            "title": "Senior Full Stack Engineer",
            "href": "https://example.com/role",
            "body": "Requires React, Python, and LLM APIs.",
        }
    ]
    out = search_web(
        "senior full stack AI engineer requirements",
        max_results=3,
        current_year=2026,
    )
    assert out["query"] == "senior full stack AI engineer requirements 2026"
    mock_ddgs_cls.return_value.text.assert_called_once_with(
        query="senior full stack AI engineer requirements 2026",
        region="us-en",
        max_results=3,
        backend="auto",
    )
    assert out["result_count"] == 1
    assert out["results"][0]["title"] == "Senior Full Stack Engineer"
    assert out["results"][0]["url"] == "https://example.com/role"
    assert "LLM APIs" in out["results"][0]["snippet"]


@patch("app.agents.web_search.DDGS")
def test_search_web_handles_errors(mock_ddgs_cls):
    mock_ddgs_cls.return_value.text.side_effect = RuntimeError("rate limited")
    out = search_web("test query")
    assert out["result_count"] == 0
    assert "rate limited" in out["error"]