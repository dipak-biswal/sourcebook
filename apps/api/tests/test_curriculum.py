"""Curriculum topic catalog, intake, and goal composition."""

from app.curriculum.compose import compose_goal
from app.curriculum.domain import domain_label, is_curriculum_workspace
from app.curriculum.discover import _fallback_topics
from app.curriculum.intake import intake_questions, normalize_answers, validate_required
from app.curriculum.schema import normalize_curriculum, normalize_topic, slugify
from app.curriculum.validate_custom import _heuristic_related


def test_is_curriculum_workspace_learning_signals():
    assert is_curriculum_workspace(name="System Design", description="Learn distributed systems")
    assert is_curriculum_workspace(name="Job stuff", tags=["learning"])
    assert not is_curriculum_workspace(
        name="Job Search 2026",
        description="Prepare applications for senior roles",
        tags=["hiring"],
    )


def test_domain_label_prefers_name():
    assert domain_label(name="System Design", description="x") == "System Design"


def test_fallback_topics_system_design():
    topics = _fallback_topics("Learn System Design interviews")
    titles = {t["title"].lower() for t in topics}
    assert any("load" in t for t in titles)
    assert len(topics) >= 8


def test_normalize_and_slug():
    assert slugify("Load Balancer!") == "load-balancer"
    t = normalize_topic({"title": "Caching", "summary": "Redis", "tags": ["perf"]})
    assert t and t["id"] == "caching"
    cur = normalize_curriculum({"topics": [t], "domain": "SD"})
    assert cur["version"] == 1
    assert len(cur["topics"]) == 1


def test_intake_checkbox_only_and_required():
    form = intake_questions({"id": "caching", "title": "Caching"})
    assert form["questions"]
    assert all(q["input"] == "checkbox" for q in form["questions"])
    answers = normalize_answers(
        {"level": "intermediate", "focus": ["how_it_works", "tradeoffs"], "bogus": "x"},
        form["questions"],
    )
    assert answers["level"] == ["intermediate"]
    assert "how_it_works" in answers["focus"]
    assert "bogus" not in answers
    assert validate_required({"level": ["beginner"]}, form["questions"]) == ["focus"]
    assert not validate_required(
        {"level": ["beginner"], "focus": ["tradeoffs"]}, form["questions"]
    )


def test_compose_goal_includes_topic_and_study_sheet():
    topic = {
        "id": "load-balancer",
        "title": "Load balancer",
        "preferences": {
            "level": ["intermediate"],
            "focus": ["how_it_works", "tradeoffs"],
            "format": ["study_sheet", "diagrams"],
            "scope": ["e2e"],
        },
    }
    goal = compose_goal(topic, domain="System Design")
    assert "Load balancer" in goal
    assert "Intermediate" in goal
    assert "study sheet" in goal.lower() or "numbered" in goal.lower()
    assert "## 1" in goal or "numbered markdown" in goal


def test_heuristic_off_topic():
    assert not _heuristic_related("chocolate cake recipes", "System Design")
    assert _heuristic_related("consistent hashing", "System Design distributed systems")


def test_normalize_preserves_archived_status():
    cur = normalize_curriculum(
        {
            "domain": "SD",
            "topics": [
                {"title": "Caching", "status": "active"},
                {"title": "Old topic", "id": "old", "status": "archived"},
            ],
        }
    )
    statuses = {t["id"]: t["status"] for t in cur["topics"]}
    assert statuses.get("caching") == "active" or any(
        t["status"] == "active" for t in cur["topics"] if "Cach" in t["title"]
    )
    assert any(t["status"] == "archived" for t in cur["topics"])
