"""Learn page lesson normalize + cache shape."""

from app.curriculum.schema import empty_curriculum, normalize_curriculum
from app.learn.lessons import normalize_lesson, _fallback_lesson


def test_normalize_lesson_requires_sections():
    assert normalize_lesson({"title": "X", "sections": []}) is None
    ok = normalize_lesson(
        {
            "title": "Optimizers",
            "summary": "Update params to minimize loss.",
            "prerequisites": ["Gradient descent"],
            "key_terms": [{"term": "SGD", "definition": "Stochastic gradient descent"}],
            "sections": [
                {
                    "id": "intro",
                    "heading": "Intro",
                    "body_md": "Optimizers step parameters.",
                    "visual_id": "v1",
                },
                {
                    "id": "sgd",
                    "heading": "SGD",
                    "body_md": "Step proportional to gradient.",
                    "visual_id": "v1",
                },
            ],
            "visuals": [
                {
                    "id": "v1",
                    "type": "key_points",
                    "title": "Ideas",
                    "body": "",
                    "items": ["SGD", "Adam", "RMSprop"],
                }
            ],
        }
    )
    assert ok is not None
    assert ok["title"] == "Optimizers"
    assert len(ok["sections"]) == 2
    assert len(ok["outline"]) == 2
    assert ok["visuals"][0]["type"] == "key_points"


def test_fallback_lesson_shape():
    lesson = _fallback_lesson(
        {"id": "outbox", "title": "Outbox pattern", "summary": "Reliable dual write."},
        "System Design",
    )
    assert lesson["title"] == "Outbox pattern"
    assert len(lesson["sections"]) >= 2
    assert lesson["visuals"]


def test_curriculum_preserves_lessons():
    cur = empty_curriculum(domain="ML")
    cur["lessons"] = {
        "optimizers": {
            "title": "Optimizers",
            "sections": [
                {"id": "a", "heading": "A", "body_md": "text a"},
                {"id": "b", "heading": "B", "body_md": "text b"},
            ],
            "visuals": [],
        }
    }
    norm = normalize_curriculum(cur)
    assert "optimizers" in norm["lessons"]
