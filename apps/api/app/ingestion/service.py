from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.chunking import chunk_text
from app.ingestion.embeddings import embed_texts
from app.ingestion.parsers import ParseError, parse_file
from app.models import Document, Chunk


def document_disk_path(doc: Document) -> Path:
    return Path(settings.upload_dir) / doc.storage_key


def extract_text(doc: Document) -> str:
    path = document_disk_path(doc)
    text = parse_file(path)
    if not text.strip():
        raise ParseError("Document is empty")
    return text


def ingest_document_chunks(
    db: Session, doc: Document, *, chunk_size: int = 800, chunk_overlap: int = 150
) -> list[Chunk]:
    text = extract_text(doc)

    db.query(Chunk).filter(Chunk.document_id == doc.id).delete()

    text_chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    vectors = embed_texts([tc.content for tc in text_chunks])

    rows: list[Chunk] = []
    for tc, vector in zip(text_chunks, vectors, strict=True):
        row = Chunk(
            document_id=doc.id,
            workspace_id=doc.workspace_id,
            chunk_index=tc.chunk_index,
            content=tc.content,
            token_count=tc.token_count,
            embedding=vector,
        )
        db.add(row)
        rows.append(row)

    doc.status = "ready"

    db.commit()

    for row in rows:
        db.refresh(row)
    db.refresh(doc)
    return rows
