"""Web search helper (Tavily primary, DuckDuckGo fallback)."""

from unittest.mock import MagicMock, patch

from app.agents.main.tools.web_search import normalize_web_search_query, search_web


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


@patch("app.agents.main.tools.web_search.settings")
@patch("app.agents.main.tools.web_search.DDGS")
def test_search_web_ddgs_normalizes_results(mock_ddgs_cls, mock_settings):
    mock_settings.web_search_provider = "ddgs"
    mock_settings.tavily_api_key = ""
    mock_settings.tavily_fallback_to_ddgs = True
    mock_settings.tavily_search_depth = "basic"
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
    assert out["provider"] == "ddgs"
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


@patch("app.agents.main.tools.web_search.settings")
@patch("app.agents.main.tools.web_search.DDGS")
def test_search_web_ddgs_handles_errors(mock_ddgs_cls, mock_settings):
    mock_settings.web_search_provider = "ddgs"
    mock_settings.tavily_api_key = ""
    mock_settings.tavily_fallback_to_ddgs = True
    mock_settings.tavily_search_depth = "basic"
    mock_ddgs_cls.return_value.text.side_effect = RuntimeError("rate limited")
    out = search_web("test query")
    assert out["result_count"] == 0
    assert "rate limited" in out["error"]
    assert out["provider"] == "ddgs"


@patch("app.agents.main.tools.web_search.settings")
@patch("app.agents.main.tools.web_search.httpx.Client")
def test_search_web_tavily_normalizes_results(mock_client_cls, mock_settings):
    mock_settings.web_search_provider = "tavily"
    mock_settings.tavily_api_key = "tvly-test"
    mock_settings.tavily_fallback_to_ddgs = False
    mock_settings.tavily_search_depth = "basic"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "query": "python async await",
        "results": [
            {
                "title": "Async IO",
                "url": "https://docs.python.org/3/library/asyncio.html",
                "content": "asyncio is a library to write concurrent code using async/await.",
                "score": 0.9,
            }
        ],
        "usage": {"credits": 1},
    }
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    out = search_web("python async await", max_results=5, current_year=2026)
    assert out["provider"] == "tavily"
    assert out["result_count"] == 1
    assert out["results"][0]["title"] == "Async IO"
    assert out["results"][0]["url"].startswith("https://docs.python.org")
    assert "async/await" in out["results"][0]["snippet"]
    assert out.get("credits_used") == 1
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs.kwargs["json"]["search_depth"] == "basic"
    assert call_kwargs.kwargs["json"]["include_answer"] is False


@patch("app.agents.main.tools.web_search.settings")
@patch("app.agents.main.tools.web_search.httpx.Client")
def test_search_web_tavily_credit_limit(mock_client_cls, mock_settings):
    mock_settings.web_search_provider = "tavily"
    mock_settings.tavily_api_key = "tvly-test"
    mock_settings.tavily_fallback_to_ddgs = False
    mock_settings.tavily_search_depth = "basic"

    mock_resp = MagicMock()
    mock_resp.status_code = 432
    mock_resp.json.return_value = {"detail": {"error": "plan limit"}}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    out = search_web("anything")
    assert out["result_count"] == 0
    assert "credit" in out["error"].lower() or "plan" in out["error"].lower()
    assert out["provider"] == "tavily"


@patch("app.agents.main.tools.web_search.settings")
@patch("app.agents.main.tools.web_search.DDGS")
@patch("app.agents.main.tools.web_search.httpx.Client")
def test_search_web_auto_falls_back_to_ddgs(
    mock_client_cls, mock_ddgs_cls, mock_settings
):
    mock_settings.web_search_provider = "auto"
    mock_settings.tavily_api_key = "tvly-test"
    mock_settings.tavily_fallback_to_ddgs = True
    mock_settings.tavily_search_depth = "basic"

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.json.return_value = {"detail": {"error": "rate limited"}}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    mock_ddgs_cls.return_value.text.return_value = [
        {
            "title": "Fallback Hit",
            "href": "https://example.com/fb",
            "body": "From DuckDuckGo",
        }
    ]

    out = search_web("test query")
    assert out["provider"] == "ddgs"
    assert out.get("fallback_from") == "tavily"
    assert out["result_count"] == 1
    assert out["results"][0]["title"] == "Fallback Hit"


@patch("app.agents.main.tools.web_search.settings")
def test_search_web_auto_without_key_uses_ddgs(mock_settings):
    mock_settings.web_search_provider = "auto"
    mock_settings.tavily_api_key = ""
    mock_settings.tavily_fallback_to_ddgs = True
    mock_settings.tavily_search_depth = "basic"

    with patch("app.agents.main.tools.web_search.DDGS") as mock_ddgs_cls:
        mock_ddgs_cls.return_value.text.return_value = [
            {"title": "A", "href": "https://a.example", "body": "b"}
        ]
        out = search_web("hello world")
    assert out["provider"] == "ddgs"
    assert out["result_count"] == 1
