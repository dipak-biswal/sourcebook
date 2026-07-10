from dataclasses import dataclass


@dataclass
class TextChunk:
    chunk_index: int
    content: str
    token_count: int


def chunk_text(
    text: str, chunk_size: int = 800, chunk_overlap: int = 150
) -> list[TextChunk]:
    """
    Character based sliding window.
    chunk_size / overlap are in characters
    """
    text = text.strip()
    if not text:
        return []
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    chunks: list[TextChunk] = []
    start = 0
    i = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)
        piece = text[start:end].strip()
        if piece:
            chunks.append(
                TextChunk(chunk_index=i, content=piece, token_count=len(piece.split()))
            )
            i += 1
        if end >= n:
            break
        start = end - chunk_overlap

    return chunks
