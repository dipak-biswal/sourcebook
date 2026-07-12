"""Smoke tests for multi-format document parsers."""

from pathlib import Path

import pytest

from app.ingestion.parsers import (
    ParseError,
    is_supported_filename,
    parse_file,
    supported_types_message,
)


def test_supported_filenames():
    assert is_supported_filename("a.pdf")
    assert is_supported_filename("b.DOCX")
    assert is_supported_filename("c.md")
    assert not is_supported_filename("d.doc")  # legacy OLE
    assert not is_supported_filename("e.png")


def test_parse_txt(tmp_path: Path):
    p = tmp_path / "note.txt"
    p.write_text("Hello Sourcebook\n\nSecond line.", encoding="utf-8")
    text = parse_file(p)
    assert "Hello Sourcebook" in text
    assert "Second line" in text


def test_parse_md(tmp_path: Path):
    p = tmp_path / "doc.md"
    p.write_text("# Title\n\nParagraph.", encoding="utf-8")
    assert "Title" in parse_file(p)


def test_parse_json(tmp_path: Path):
    p = tmp_path / "data.json"
    p.write_text('{"a": 1, "b": "x"}', encoding="utf-8")
    text = parse_file(p)
    assert '"a"' in text


def test_parse_html_strips_tags(tmp_path: Path):
    p = tmp_path / "page.html"
    p.write_text(
        "<html><body><h1>Hello</h1><script>x=1</script><p>World</p></body></html>",
        encoding="utf-8",
    )
    text = parse_file(p)
    assert "Hello" in text
    assert "World" in text
    assert "<script>" not in text


def test_empty_txt_fails(tmp_path: Path):
    p = tmp_path / "empty.txt"
    p.write_text("   \n  ", encoding="utf-8")
    with pytest.raises(ParseError, match="No extractable text"):
        parse_file(p)


def test_unsupported_suffix(tmp_path: Path):
    p = tmp_path / "img.png"
    p.write_bytes(b"\x89PNG")
    with pytest.raises(ParseError, match="Unsupported"):
        parse_file(p)


def test_supported_types_message_mentions_pdf():
    msg = supported_types_message()
    assert "PDF" in msg
    assert "DOCX" in msg
