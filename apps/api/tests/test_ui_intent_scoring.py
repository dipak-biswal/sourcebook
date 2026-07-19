"""UiIntent scoring config + offline eval set (#11) and interaction boosts (#13)."""

from types import SimpleNamespace

from app.presentation.interactions import boosts_from_interaction_rows
from app.presentation.ui_intent import (
    DEFAULT_SCORING,
    UiIntentScoringConfig,
    resolve_ui_intent,
)


# Offline eval set: (structured, packet, goal, must_include_early) fixtures.
# "must_include_early" affordances should appear in the first half of block_order.
_EVAL_SET: list[dict] = [
    {
        "name": "learning_how_to",
        "structured": {
            "summary": "Distributed systems coordinate independent nodes.",
            "key_points": ["Partial failure is normal", "Replication scales reads"],
            "faq": [{"question": "Is CAP absolute?", "answer": "No."}],
            "sections": [
                {
                    "heading": "Design steps",
                    "bullets": ["Requirements", "API", "Data model", "Tradeoffs"],
                }
            ],
            "themes": ["fundamentals", "consistency"],
        },
        "packet": {
            "derived": {
                "visual_affordances": [
                    "overview",
                    "concept_glossary",
                    "ordered_guide",
                    "self_check",
                ]
            }
        },
        "goal": "How do I design a simple scalable system?",
        "must_include_early": ["ordered_guide"],
    },
    {
        "name": "career_compare",
        "structured": {
            "summary": "React evidence is strong; cloud keywords are thin.",
            "key_points": ["React is strong", "AWS is a gap"],
            "faq": [{"question": "Keyword stuffing?", "answer": "Avoid it."}],
            "matrix_rows": [
                "Requirement | Evidence | Status",
                "React | Lead role | Strong",
                "AWS | Mentioned once | Gap",
            ],
            "levels": ["React | Strong", "AWS | Gap"],
            "sections": [
                {
                    "heading": "Update checklist",
                    "bullets": ["Add Skills line", "Rewrite bullets", "Export PDF"],
                }
            ],
        },
        "packet": {
            "derived": {
                "visual_affordances": [
                    "overview",
                    "priority_alert",
                    "comparison_matrix",
                    "qualitative_levels",
                    "ordered_guide",
                ]
            }
        },
        "goal": "Compare my resume to the job description",
        "must_include_early": ["comparison_matrix"],
    },
    {
        "name": "timeline_goal",
        "structured": {
            "summary": "Project evolved over three years.",
            "key_points": ["MVP first", "Then scale"],
            "milestones": [
                "2021 | Prototype",
                "2022 | Beta",
                "2023 | GA",
            ],
            "faq": [],
            "sections": [],
        },
        "packet": {
            "derived": {
                "visual_affordances": ["overview", "timeline", "highlights"]
            }
        },
        "goal": "Show the product timeline and milestones",
        "must_include_early": ["timeline"],
    },
]


def test_default_scoring_constants_are_stable():
    """Pin the production weights so accidental renames fail loudly."""
    assert DEFAULT_SCORING.workspace_rank_base == 10.0
    assert DEFAULT_SCORING.workspace_rank_decay == 0.5
    assert DEFAULT_SCORING.hint_boost == 2.0
    assert DEFAULT_SCORING.goal_boost == 1.5
    assert DEFAULT_SCORING.interaction_boost_cap == 3.0
    assert DEFAULT_SCORING.outline_cap == 8


def test_eval_set_orders_expected_affordances_early():
    for case in _EVAL_SET:
        intent = resolve_ui_intent(
            structured_content=case["structured"],
            workspace_packet=case["packet"],
            goal=case["goal"],
        )
        half = max(1, len(intent.block_order) // 2 + 1)
        early = set(intent.block_order[:half])
        for aff in case["must_include_early"]:
            assert aff in intent.block_order, (
                f"{case['name']}: {aff} missing from {intent.block_order}"
            )
            assert aff in early or intent.block_order[0] == aff, (
                f"{case['name']}: {aff} not early enough in {intent.block_order}"
            )


def test_scoring_config_goal_boost_is_tunable():
    structured = {
        "summary": "Overview text for scoring.",
        "key_points": ["A", "B", "C"],
        "faq": [
            {"question": "Q1?", "answer": "A1."},
            {"question": "Q2?", "answer": "A2."},
        ],
        "sections": [],
    }
    packet = {
        "derived": {
            "visual_affordances": ["overview", "highlights", "self_check"]
        }
    }
    # layout_components_from_goal maps "faq" → self_check via _goal_boost.
    low = resolve_ui_intent(
        structured_content=structured,
        workspace_packet=packet,
        goal="Summarize with an FAQ section",
        scoring=UiIntentScoringConfig(goal_boost=0.0),
    )
    high = resolve_ui_intent(
        structured_content=structured,
        workspace_packet=packet,
        goal="Summarize with an FAQ section",
        scoring=UiIntentScoringConfig(goal_boost=5.0),
    )
    assert high.scores.get("self_check", 0) > low.scores.get("self_check", 0)


def test_interaction_boosts_promote_affordance():
    structured = {
        "summary": "Overview text for interaction ranking.",
        "key_points": ["A", "B"],
        "faq": [
            {"question": "Q1?", "answer": "A1."},
            {"question": "Q2?", "answer": "A2."},
        ],
        "themes": ["alpha", "beta", "gamma"],
    }
    packet = {
        "derived": {
            "visual_affordances": ["overview", "highlights", "self_check", "topic_filter"]
        }
    }
    base = resolve_ui_intent(
        structured_content=structured,
        workspace_packet=packet,
        goal="Summarize the workspace",
    )
    boosted = resolve_ui_intent(
        structured_content=structured,
        workspace_packet=packet,
        goal="Summarize the workspace",
        interaction_boosts={"self_check": 3.0, "topic_filter": 2.5},
    )
    assert boosted.scores["self_check"] > base.scores["self_check"]
    assert boosted.scores["topic_filter"] > base.scores["topic_filter"]
    # FAQ (self_check) should move earlier when heavily interacted with.
    assert boosted.block_order.index("self_check") <= base.block_order.index("self_check")


def test_boosts_from_interaction_rows_fold():
    rows = [
        SimpleNamespace(meta={"action": "faq_expand", "affordance": "self_check"}),
        SimpleNamespace(meta={"action": "faq_expand"}),
        SimpleNamespace(meta={"action": "chip_select", "affordance": "topic_filter"}),
        SimpleNamespace(meta={"action": "unknown"}),
        SimpleNamespace(meta=None),
    ]
    boosts = boosts_from_interaction_rows(rows)
    assert "self_check" in boosts
    assert "topic_filter" in boosts
    assert boosts["self_check"] > boosts["topic_filter"]  # 2 clicks > 1
