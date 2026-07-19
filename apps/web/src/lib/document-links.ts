/** Deep-link helpers for document / chunk citation navigation. */

export function documentViewerPath(
  documentId: string,
  opts?: { chunkId?: string | null; highlight?: string | null },
): string {
  const params = new URLSearchParams();
  if (opts?.chunkId) params.set("chunk", opts.chunkId);
  if (opts?.highlight) params.set("q", opts.highlight.slice(0, 80));
  const qs = params.toString();
  return qs ? `/documents/${documentId}?${qs}` : `/documents/${documentId}`;
}

export type CitationLike = {
  document_id?: string | null;
  chunk_id?: string | null;
  filename?: string | null;
  snippet?: string | null;
};

/** Best path for a citation; null when we have no document id. */
export function citationViewerPath(c: CitationLike): string | null {
  if (!c.document_id) return null;
  return documentViewerPath(c.document_id, {
    chunkId: c.chunk_id,
    highlight: c.snippet,
  });
}
