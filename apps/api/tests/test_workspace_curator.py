"""Workspace Curator agent: URL normalize + schema source_urls."""

from app.agents.workspace_curator.agent import _normalize_urls, _attach_source_urls_to_topics
from app.curriculum.schema import normalize_curriculum, normalize_topic


def test_normalize_urls_dedupes_and_https():
    urls = _normalize_urls(
        [
            "https://example.com/a",
            "https://example.com/a/",
            "example.com/b",
            "not a url",
            "",
        ]
    )
    assert "https://example.com/a" in urls
    assert any("example.com/b" in u for u in urls)
    assert len(urls) <= 2


def test_topic_preserves_source_urls():
    t = normalize_topic(
        {
            "title": "Load balancer",
            "summary": "Distribute traffic",
            "source_urls": ["https://example.com/lb", "ftp://bad"],
        }
    )
    assert t is not None
    assert t["source_urls"] == ["https://example.com/lb"]


def test_curriculum_preserves_sources_list():
    cur = normalize_curriculum(
        {
            "domain": "System Design",
            "source_urls": ["https://a.example/docs", "https://b.example/toc"],
            "sources": [
                {
                    "url": "https://a.example/docs",
                    "title": "Docs",
                    "ok": True,
                    "chars": 100,
                }
            ],
            "topics": [
                {
                    "title": "Caching",
                    "summary": "Speed reads",
                    "source_urls": ["https://a.example/docs"],
                }
            ],
        }
    )
    assert cur["docs_url"] == "https://a.example/docs"
    assert len(cur["source_urls"]) == 2
    assert cur["sources"][0]["url"] == "https://a.example/docs"
    assert cur["topics"][0]["source_urls"] == ["https://a.example/docs"]


def test_attach_source_urls_by_title():
    chapters = [
        {
            "title": "Scalability",
            "source_urls": ["https://a.example"],
            "children": [
                {
                    "title": "Caching",
                    "source_urls": ["https://a.example"],
                    "summary": "x",
                    "tags": [],
                }
            ],
            "summary": "y",
            "tags": [],
        }
    ]
    flat = [
        {"id": "scalability", "title": "Scalability", "parent_id": None},
        {"id": "caching", "title": "Caching", "parent_id": "scalability"},
    ]
    out = _attach_source_urls_to_topics(flat, chapters, {"https://a.example"})
    assert out[0]["source_urls"] == ["https://a.example"]
    assert out[1]["source_urls"] == ["https://a.example"]
