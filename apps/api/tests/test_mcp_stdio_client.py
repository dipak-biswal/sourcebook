"""Unit tests for MCP stdio helpers (no live npx process)."""

from app.mcp.stdio_client import extract_urls, parse_tool_text_content


def test_parse_tool_text_content():
    text = parse_tool_text_content(
        {
            "content": [
                {
                    "type": "text",
                    "text": "Draw.io Editor URL:\nhttps://app.diagrams.net/?x=1#create=abc\n",
                }
            ]
        }
    )
    assert "diagrams.net" in text


def test_extract_urls_strips_punctuation():
    urls = extract_urls("See https://example.com/a). Next https://app.diagrams.net/x.")
    assert urls[0] == "https://example.com/a"
    assert urls[1].startswith("https://app.diagrams.net/")
