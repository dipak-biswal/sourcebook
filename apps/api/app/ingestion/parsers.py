from pathlib import Path


SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}


class ParseError(Exception):
    """Raised when a document cannot be parsed."""


def parse_file(path: Path) -> str:
    """Read a local file and return plain text."""
    if not path.is_file():
        raise ParseError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_TEXT_SUFFIXES:
        raise ParseError(
            f"Unsupported type '{suffix}'. Week 2 supports: {sorted(SUPPORTED_TEXT_SUFFIXES)}"
        )

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
