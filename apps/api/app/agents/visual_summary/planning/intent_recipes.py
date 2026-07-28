"""Intent → UI recipes (genui-demo style): purpose-built layouts, not generic dumps.

Maps goal + optional curriculum topic prefs to a concrete block outline recipe
and content contract for the main agent / study-sheet planner.
"""

from __future__ import annotations

import re
from typing import Any

# Recipe ids used in assembly_meta / plan rationale.
RECIPE_MECHANISM = "mechanism"  # how it works
RECIPE_TRADEOFFS = "tradeoffs"  # without vs with / compare
RECIPE_CHECKLIST = "checklist"  # how-to / practices
RECIPE_COMPARISON = "comparison"  # option cards / table
RECIPE_STUDY_FULL = "study_full"  # full learning arc
RECIPE_METRICS = "metrics"
RECIPE_DEFAULT = "default"


def _prefs(prefs: dict[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(prefs, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in prefs.items():
        if isinstance(v, list):
            out[str(k)] = [str(x) for x in v if str(x).strip()]
        elif v is not None and str(v).strip():
            out[str(k)] = [str(v).strip()]
    return out


def resolve_recipe(
    *,
    goal: str = "",
    topic_title: str = "",
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Return a recipe dict:
      id, title, lead_blocks[], required_sections[], content_rules[], outline_hint[]
    """
    g = f"{goal}\n{topic_title}".lower()
    prefs = _prefs(preferences)
    focus = set(prefs.get("focus") or [])
    fmt = set(prefs.get("format") or [])

    # Curriculum focus wins when present.
    if "tradeoffs" in focus or "failure_modes" in focus:
        return _recipe_tradeoffs(topic_title or goal)
    if "how_it_works" in focus or "architecture" in focus:
        return _recipe_mechanism(topic_title or goal)
    if "example" in focus or "interview" in focus:
        return _recipe_study_full(topic_title or goal)
    if "study_sheet" in fmt or "diagrams" in fmt:
        return _recipe_study_full(topic_title or goal)
    if "checklist" in fmt:
        return _recipe_checklist(topic_title or goal)
    if "comparisons" in fmt:
        return _recipe_comparison(topic_title or goal)

    # Goal phrasing (demo-style intent matching).
    if re.search(r"\b(compare|versus|vs\.?|which (is|one)|trade[- ]?off)\b", g):
        return _recipe_comparison(topic_title or goal)
    if re.search(r"\b(how does|how it works|mechanism|lifecycle|under the hood)\b", g):
        return _recipe_mechanism(topic_title or goal)
    if re.search(r"\b(how to|checklist|steps?|best practices?|implement)\b", g):
        return _recipe_checklist(topic_title or goal)
    if re.search(r"\b(metric|latency|throughput|score|percent|gauge)\b", g):
        return _recipe_metrics(topic_title or goal)
    if re.search(
        r"\b(study sheet|complete guide|teach|learn|deep dive|end[\s-]?to[\s-]?end)\b",
        g,
    ):
        return _recipe_study_full(topic_title or goal)

    return _recipe_default(topic_title or goal)


def _base(
    rid: str,
    title: str,
    *,
    lead: list[str],
    sections: list[str],
    rules: list[str],
    outline: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "id": rid,
        "title": title[:120],
        "lead_blocks": lead,
        "required_sections": sections,
        "content_rules": rules,
        "outline_hint": outline,
    }


def _recipe_mechanism(topic: str) -> dict[str, Any]:
    t = topic.strip() or "this topic"
    return _base(
        RECIPE_MECHANISM,
        t,
        lead=["flow_diagram", "sequence_diagram", "key_points"],
        sections=[
            f"1. What is {t} (one concrete definition)",
            "2. High-level flow (named components, A → B → C)",
            "3. Step-by-step with real names (not 'Service A')",
            "4. Failure / edge cases table",
            "5. When to use",
        ],
        rules=[
            "Use real component names (e.g. OrderService, OutboxProcessor, Kafka).",
            "Every process must include an A → B → C chain or numbered steps.",
            "No filler: avoid 'it depends', 'various factors', 'in many systems' without specifics.",
            "Include at least one pipe table for failures or options.",
        ],
        outline=[
            {"type": "summary", "purpose": "concrete definition"},
            {"type": "flow_diagram", "purpose": "pipeline"},
            {"type": "steps", "purpose": "walkthrough"},
            {"type": "table", "purpose": "failures"},
            {"type": "key_points", "purpose": "when to use"},
        ],
    )


def _recipe_tradeoffs(topic: str) -> dict[str, Any]:
    t = topic.strip() or "this approach"
    return _base(
        RECIPE_TRADEOFFS,
        t,
        lead=["compare_paths", "comparison", "table", "callout"],
        sections=[
            f"1. Why {t} matters",
            "2. Without vs With (dual paths + outcomes)",
            "3. Tradeoff matrix (criteria | option A | option B)",
            "4. Concrete recommendation with conditions",
        ],
        rules=[
            "Without vs With must name concrete steps and failure outcomes.",
            "Tradeoff table: at least 3 criteria rows with specific cells (not 'better'/'worse').",
            "End with a clear recommendation and when it does NOT apply.",
        ],
        outline=[
            {"type": "summary", "purpose": "why it matters"},
            {"type": "compare_paths", "purpose": "without vs with"},
            {"type": "table", "purpose": "tradeoff matrix"},
            {"type": "callout", "purpose": "recommendation"},
        ],
    )


def _recipe_comparison(topic: str) -> dict[str, Any]:
    t = topic.strip() or "options"
    return _base(
        RECIPE_COMPARISON,
        t,
        lead=["option_cards", "table", "callout"],
        sections=[
            f"1. What we are comparing ({t})",
            "2. Option cards (name | tag | key metric | 2 bullets each)",
            "3. Side-by-side matrix",
            "4. Pick recommendation",
        ],
        rules=[
            "Each option needs a short tag (Cheapest, Fastest, Safest, etc.) and one numeric or crisp metric.",
            "Use OptionName | Tag | Metric | Detail pipe rows for option cards.",
            "No vague cells like 'good' or 'depends' without a condition.",
        ],
        outline=[
            {"type": "summary", "purpose": "frame"},
            {"type": "option_cards", "purpose": "selectable options"},
            {"type": "table", "purpose": "matrix"},
            {"type": "callout", "purpose": "pick"},
        ],
    )


def _recipe_checklist(topic: str) -> dict[str, Any]:
    t = topic.strip() or "this task"
    return _base(
        RECIPE_CHECKLIST,
        t,
        lead=["steps", "callout", "key_points"],
        sections=[
            f"1. Goal for {t}",
            "2. Ordered checklist (actionable verbs)",
            "3. Common mistakes",
            "4. Done-when criteria",
        ],
        rules=[
            "Every checklist item starts with a verb and is implementable in one sitting.",
            "Include 5–10 steps, not 2–3 vague phases.",
        ],
        outline=[
            {"type": "summary", "purpose": "goal"},
            {"type": "steps", "purpose": "checklist"},
            {"type": "callout", "purpose": "mistakes"},
            {"type": "key_points", "purpose": "done-when"},
        ],
    )


def _recipe_metrics(topic: str) -> dict[str, Any]:
    t = topic.strip() or "metrics"
    return _base(
        RECIPE_METRICS,
        t,
        lead=["metrics", "chart", "progress", "key_points"],
        sections=[
            f"1. What we measure for {t}",
            "2. Metrics (Label | value with unit)",
            "3. How to read them",
            "4. Targets / next actions",
        ],
        rules=[
            "Every metric row is Label | number unit (e.g. Latency | 45 ms).",
            "Include at least 3 metrics with real numbers when known, or clear ranges.",
        ],
        outline=[
            {"type": "summary", "purpose": "frame"},
            {"type": "metrics", "purpose": "gauges"},
            {"type": "chart", "purpose": "bars"},
            {"type": "steps", "purpose": "actions"},
        ],
    )


def _recipe_study_full(topic: str) -> dict[str, Any]:
    t = topic.strip() or "this topic"
    return _base(
        RECIPE_STUDY_FULL,
        t,
        lead=[
            "summary",
            "flow_diagram",
            "compare_paths",
            "table",
            "steps",
            "key_points",
        ],
        sections=[
            f"1. Why {t} (problem it solves — concrete)",
            "2. High-level flow (named components A → B → C)",
            "3. Without vs With (dual outcomes)",
            "4. Data / schema or config example (pipe table)",
            "5. Options / variants",
            "6. Consumer / side effects",
            "7. Transaction or consistency boundaries (steps)",
            "8. Failure scenarios (Failure | Problem | Handling)",
            "9. Best practices (actionable bullets)",
            "10. End-to-end example with real names",
            "11. When to use / when not",
            "12. Summary takeaways",
        ],
        rules=[
            "Write for a study board: dense, concrete, scannable — not an essay.",
            "Name real systems/components (Kafka, Postgres, OrderService) not placeholders.",
            "Must include: A → B → C chain, one Without|With or dual path, one multi-column table.",
            "Ban vague phrases: 'various', 'it depends' (unless followed by 2+ concrete cases), 'important to consider'.",
            "Each section needs 2+ real facts or steps, not a single sentence restating the title.",
        ],
        outline=[
            {"type": "summary", "purpose": "why"},
            {"type": "flow_diagram", "purpose": "flow"},
            {"type": "compare_paths", "purpose": "without vs with"},
            {"type": "table", "purpose": "schema or failures"},
            {"type": "steps", "purpose": "boundaries"},
            {"type": "key_points", "purpose": "practices"},
        ],
    )


def _recipe_default(topic: str) -> dict[str, Any]:
    t = topic.strip() or "this goal"
    return _base(
        RECIPE_DEFAULT,
        t,
        lead=["summary", "key_points", "steps"],
        sections=[
            "1. Direct answer",
            "2. Supporting points (specific)",
            "3. Next actions",
        ],
        rules=[
            "Lead with a concrete answer in the first 2 sentences.",
            "Prefer tables and steps over long paragraphs.",
        ],
        outline=[
            {"type": "summary", "purpose": "answer"},
            {"type": "key_points", "purpose": "support"},
            {"type": "steps", "purpose": "actions"},
        ],
    )


def apply_recipe_to_study_outline(
    outline: list[dict[str, Any]],
    recipe: dict[str, Any],
) -> list[dict[str, Any]]:
    """Annotate panels with recipe id — never reorder numbered study boards.

    Block types are already inferred from section content. Recipes drive the
    main-agent content contract; scrambling panel order made boards feel
    random relative to ## 1. / ## 2. teaching arcs.
    """
    if not outline:
        return outline
    rid = str((recipe or {}).get("id") or "").strip()
    if not rid:
        return outline
    for entry in outline:
        if isinstance(entry, dict):
            entry["recipe"] = rid
    return outline


def content_contract_for_prompt(recipe: dict[str, Any]) -> str:
    """Text block injected into main-agent goal / curriculum context."""
    if not recipe:
        return ""
    lines = [
        "VISUAL / CONTENT CONTRACT (must follow — visual UI is built from this):",
        f"- Recipe: {recipe.get('id')} for «{recipe.get('title')}»",
        "- Required section arc:",
    ]
    for s in recipe.get("required_sections") or []:
        lines.append(f"  · {s}")
    lines.append("- Hard rules:")
    for r in recipe.get("content_rules") or []:
        lines.append(f"  · {r}")
    lines.append(
        "- Output ONLY structured teaching content (markdown). "
        "Do not name UI widgets."
    )
    return "\n".join(lines)
