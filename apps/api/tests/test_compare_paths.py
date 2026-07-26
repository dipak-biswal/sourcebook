"""compare_paths block: Without vs With dual-path diagrams."""

from app.agents.visual_summary.planning.study_sheet import infer_section_block_type
from app.agents.visual_summary.render.assemble import (
    _compare_paths_from_section,
    assemble_blocks,
)
from app.agents.visual_summary.blocks.gen_ui import _normalize_block_dict


def test_infer_without_vs_with_is_compare_paths():
    assert (
        infer_section_block_type(
            {
                "heading": "3. Without vs With Outbox Pattern",
                "body": "Without outbox, publish can fail and lose the message.",
                "bullets": [
                    "DB then publish | DB + outbox in one txn",
                    "Message may be lost | Eventually delivered",
                ],
            }
        )
        == "compare_paths"
    )


def test_compare_paths_from_section_builds_fail_edge():
    sec = {
        "heading": "Without vs With",
        "body": "Without outbox messages can be lost.",
        "bullets": [
            "Update DB | Publish | Broker",
            "Message may be lost | Eventually delivered",
        ],
    }
    paths = _compare_paths_from_section(sec, {"key_points": []})
    assert paths is not None and len(paths) == 2
    without = paths[0]
    assert without.edges
    assert any(e.style == "fail" for e in without.edges)
    assert without.result


def test_assemble_compare_paths_block():
    structured = {
        "summary": "Outbox",
        "sections": [
            {
                "heading": "3. Without vs With Outbox",
                "body": "Risk of message loss without outbox.",
                "bullets": [
                    "Update DB then publish | Update DB + insert outbox",
                    "Message may be lost | Message delivered eventually",
                ],
            }
        ],
        "key_points": [],
        "faq": [],
        "themes": [],
    }
    outline = [
        {
            "type": "compare_paths",
            "title": "3. Without vs With Outbox",
            "source_hint": "compare_paths",
            "width": "full",
            "section_index": 1,
            "panel_index": 1,
        }
    ]
    blocks, dropped = assemble_blocks(outline, structured)
    assert blocks, dropped
    b = blocks[0]
    assert b.type == "compare_paths"
    assert b.paths and len(b.paths) >= 2
    assert any(e.style == "fail" for e in b.paths[0].edges)


def test_normalize_compare_paths_keeps_style():
    raw = {
        "type": "compare_paths",
        "title": "Paths",
        "paths": [
            {
                "id": "a",
                "label": "Without",
                "nodes": [
                    {"id": "1", "label": "A"},
                    {"id": "2", "label": "B"},
                ],
                "edges": [{"source": "1", "target": "2", "style": "fail", "label": "X"}],
                "result": "Lost",
            },
            {
                "id": "b",
                "label": "With",
                "nodes": [
                    {"id": "1", "label": "A"},
                    {"id": "2", "label": "B"},
                ],
                "edges": [{"source": "1", "target": "2"}],
                "result": "OK",
            },
        ],
    }
    norm = _normalize_block_dict(raw)
    assert norm and norm["type"] == "compare_paths"
    assert norm["paths"][0]["edges"][0]["style"] == "fail"
