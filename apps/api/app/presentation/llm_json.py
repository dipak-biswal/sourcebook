"""Strict structured-output helpers for the visual pipeline LLM calls.

chat_json prefers response_format=json_schema (strict) and falls back to
json_object when the provider rejects it, so alternative OpenAI-compatible
backends keep working. Schemas derive from the block registry — the enums
below cannot drift from app.blocks.
"""

from __future__ import annotations

from typing import Any

from openai import BadRequestError

from app.blocks import ALL_BLOCK_TYPES, KNOWN_SOURCE_HINTS


def _str_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "presentation_profile": {"type": "string"},
        "components": _str_array(),
        "block_outline": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(ALL_BLOCK_TYPES)},
                    "title": {"type": "string"},
                    "purpose": {"type": "string"},
                    "source_hint": {
                        "type": "string",
                        "enum": list(KNOWN_SOURCE_HINTS),
                    },
                    "width": {"type": "string", "enum": ["full", "half"]},
                },
                "required": ["type", "title", "purpose", "source_hint", "width"],
                "additionalProperties": False,
            },
        },
        "rationale": {"type": "string"},
    },
    "required": ["presentation_profile", "components", "block_outline", "rationale"],
    "additionalProperties": False,
}

STRUCTURED_CONTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": _str_array(),
        "ordered_actions": _str_array(),
        "faq": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                },
                "required": ["question", "answer"],
                "additionalProperties": False,
            },
        },
        "concepts": _str_array(),
        "levels": _str_array(),
        "matrix_rows": _str_array(),
        "comparisons": _str_array(),
        "metrics": _str_array(),
        "milestones": _str_array(),
        "priority_message": {"type": "string"},
        "process_flow": {
            "type": "object",
            "properties": {
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "label": {"type": "string"},
                            "detail": {"type": "string"},
                        },
                        "required": ["id", "label", "detail"],
                        "additionalProperties": False,
                    },
                },
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "label": {"type": "string"},
                        },
                        "required": ["source", "target", "label"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["nodes", "edges"],
            "additionalProperties": False,
        },
        "interaction_sequence": {
            "type": "object",
            "properties": {
                "actors": _str_array(),
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "label": {"type": "string"},
                            "order": {"type": "integer"},
                            "note": {"type": "string"},
                        },
                        "required": ["source", "target", "label", "order", "note"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["actors", "messages"],
            "additionalProperties": False,
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "bullets": _str_array(),
                    "body": {"type": "string"},
                },
                "required": ["heading", "bullets", "body"],
                "additionalProperties": False,
            },
        },
        "themes": _str_array(),
    },
    "required": [
        "summary",
        "key_points",
        "ordered_actions",
        "faq",
        "concepts",
        "levels",
        "matrix_rows",
        "comparisons",
        "metrics",
        "milestones",
        "priority_message",
        "process_flow",
        "interaction_sequence",
        "sections",
        "themes",
    ],
    "additionalProperties": False,
}

COMBINED_EXTRACT_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "structured_content": STRUCTURED_CONTENT_SCHEMA,
        "layout_plan": PLAN_SCHEMA,
    },
    "required": ["structured_content", "layout_plan"],
    "additionalProperties": False,
}

RENDER_PAYLOAD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "plain_summary": {"type": "string"},
        "presentation_profile": {"type": "string"},
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(ALL_BLOCK_TYPES)},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "items": _str_array(),
                    "terms": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "term": {"type": "string"},
                                "definition": {"type": "string"},
                            },
                            "required": ["term", "definition"],
                            "additionalProperties": False,
                        },
                    },
                    "faqs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "answer": {"type": "string"},
                            },
                            "required": ["question", "answer"],
                            "additionalProperties": False,
                        },
                    },
                    "tags": _str_array(),
                    "width": {"type": "string", "enum": ["full", "half"]},
                    "source_indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "nodes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                                "detail": {"type": "string"},
                            },
                            "required": ["id", "label", "detail"],
                            "additionalProperties": False,
                        },
                    },
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "target": {"type": "string"},
                                "label": {"type": "string"},
                            },
                            "required": ["source", "target", "label"],
                            "additionalProperties": False,
                        },
                    },
                    "actors": _str_array(),
                    "messages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "target": {"type": "string"},
                                "label": {"type": "string"},
                                "order": {"type": "integer"},
                                "note": {"type": "string"},
                            },
                            "required": ["source", "target", "label", "order", "note"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "type",
                    "title",
                    "body",
                    "items",
                    "terms",
                    "faqs",
                    "tags",
                    "width",
                    "source_indices",
                    "nodes",
                    "edges",
                    "actors",
                    "messages",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "plain_summary", "presentation_profile", "blocks"],
    "additionalProperties": False,
}


def chat_json(
    client: Any,
    *,
    model: str,
    system: str,
    prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    temperature: float = 0.1,
    max_tokens: int | None = None,
):
    """One JSON chat completion: strict json_schema, json_object on rejection."""
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    try:
        return client.chat.completions.create(
            **kwargs,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        )
    except (BadRequestError, TypeError):
        # Provider without json_schema support — plain JSON mode.
        return client.chat.completions.create(
            **kwargs,
            response_format={"type": "json_object"},
        )
