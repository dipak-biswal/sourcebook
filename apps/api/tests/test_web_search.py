"""DuckDuckGo web search helper."""

from unittest.mock import MagicMock, patch

from app.agents.web_search import search_web


def test_search_web_requires_query():
    out = search_web("  ")
    assert out["result_count"] == 0
    assert out["error"] == "Query is required"


@patch("duckduckgo_search.DDGS")
def test_search_web_normalizes_results(mock_ddgs_cls):
    mock_ddgs_cls.return_value.text.return_value = [
        {
            "title": "Senior Full Stack Engineer",
            "href": "https://example.com/role",
            "body": "Requires React, Python, and LLM APIs.",
        }
    ]
    out = search_web("senior full stack AI engineer requirements", max_results=3)
    assert out["query"] == "senior full stack AI engineer requirements"
    assert out["result_count"] == 1
    assert out["results"][0]["title"] == "Senior Full Stack Engineer"
    assert out["results"][0]["url"] == "https://example.com/role"
    assert "LLM APIs" in out["results"][0]["snippet"]


@patch("duckduckgo_search.DDGS")
def test_search_web_handles_errors(mock_ddgs_cls):
    mock_ddgs_cls.return_value.text.side_effect = RuntimeError("rate limited")
    out = search_web("test query")
    assert out["result_count"] == 0
    assert "rate limited" in out["error"]