"""Hierarchical learn catalog (chapters + children)."""

from app.curriculum.discover import _fallback_topics, _flatten_chapters
from app.curriculum.schema import normalize_topic


def test_flatten_chapters_sets_parent_ids():
    topics = _flatten_chapters(
        [
            {
                "title": "Scalability principles",
                "summary": "How systems grow",
                "tags": ["scalability"],
                "children": [
                    {
                        "title": "Load balancer",
                        "summary": "Distribute traffic",
                        "tags": ["networking"],
                    },
                    {
                        "title": "Caching",
                        "summary": "Speed reads",
                        "tags": ["performance"],
                    },
                ],
            }
        ],
        source="fallback",
    )
    parents = [t for t in topics if not t.get("parent_id")]
    children = [t for t in topics if t.get("parent_id")]
    assert len(parents) == 1
    assert parents[0]["kind"] == "chapter"
    assert parents[0]["title"] == "Scalability principles"
    assert len(children) == 2
    assert all(c["parent_id"] == parents[0]["id"] for c in children)
    assert all(c["kind"] == "lesson" for c in children)


def test_system_design_fallback_is_hierarchical():
    topics = _fallback_topics("System Design interview prep")
    parents = [t for t in topics if not t.get("parent_id")]
    children = [t for t in topics if t.get("parent_id")]
    assert len(parents) >= 3
    assert len(children) >= 6
    parent_ids = {p["id"] for p in parents}
    assert all(c["parent_id"] in parent_ids for c in children)


def test_normalize_topic_preserves_parent():
    t = normalize_topic(
        {
            "title": "Caching",
            "summary": "Speed reads",
            "parent_id": "scalability-principles",
            "kind": "lesson",
        }
    )
    assert t is not None
    assert t["parent_id"] == "scalability-principles"
    assert t["kind"] == "lesson"
