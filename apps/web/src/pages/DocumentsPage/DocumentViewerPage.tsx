import { useEffect, useMemo, useRef } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText, Loader2 } from "lucide-react";
import { api, type DocumentChunk } from "@/api";
import { AppHeader } from "@/components/layout/AppHeader";
import { ErrorAlert } from "@/components/ui/error-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { cn, formatError } from "@/lib/utils";

export function DocumentViewerPage() {
  const navigate = useNavigate();
  const { documentId = "" } = useParams<{ documentId: string }>();
  const [search] = useSearchParams();
  const highlightChunkId = search.get("chunk") || "";
  const highlightQuery = (search.get("q") || "").trim().toLowerCase();

  const {
    data: doc,
    error: docError,
    isLoading: docLoading,
    refetch: refetchDoc,
  } = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api.document(documentId),
    enabled: !!documentId,
  });

  const {
    data: chunks = [],
    error: chunksError,
    isLoading: chunksLoading,
    refetch: refetchChunks,
  } = useQuery({
    queryKey: ["documentChunks", documentId],
    queryFn: () => api.documentChunks(documentId),
    enabled: !!documentId,
  });

  useDocumentTitle(doc?.filename ? doc.filename : "Document");

  const activeChunkId = useMemo(() => {
    if (highlightChunkId) return highlightChunkId;
    if (!highlightQuery || !chunks.length) return "";
    const hit = chunks.find((c) =>
      (c.content || "").toLowerCase().includes(highlightQuery),
    );
    return hit?.id ?? "";
  }, [highlightChunkId, highlightQuery, chunks]);

  const activeRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!activeChunkId || !activeRef.current) return;
    activeRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [activeChunkId, chunks]);

  const loading = docLoading || chunksLoading;
  const error = docError || chunksError;

  return (
    <div className="app-shell">
      <AppHeader onLogout={() => navigate("/login", { replace: true })} />
      <main
        id="main-content"
        tabIndex={-1}
        className="document-scroll mx-auto flex min-h-0 w-full max-w-3xl flex-1 flex-col overflow-y-auto px-4 py-4 sm:px-6"
      >
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="h-8 gap-1"
            onClick={() => navigate("/documents")}
          >
            <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
            Library
          </Button>
          <Link
            to="/chat"
            className="text-[11px] font-medium text-mute underline-offset-2 hover:text-ink hover:underline"
          >
            Open chat
          </Link>
        </div>

        {error && (
          <ErrorAlert
            message={formatError(error)}
            className="mb-4"
            onRetry={() => {
              void refetchDoc();
              void refetchChunks();
            }}
          />
        )}

        {loading && !doc ? (
          <div className="flex items-center gap-2 text-sm text-mute">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading document…
          </div>
        ) : doc ? (
          <>
            <div className="mb-4 rounded-vercel-md border border-hairline bg-canvas p-4">
              <div className="flex items-start gap-2">
                <FileText
                  className="mt-0.5 h-5 w-5 shrink-0 text-ink"
                  strokeWidth={1.5}
                />
                <div className="min-w-0">
                  <h1 className="text-lg font-semibold tracking-tight text-ink">
                    {doc.filename}
                  </h1>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-mute">
                    <Badge
                      variant={
                        doc.status.toLowerCase() === "ready"
                          ? "success"
                          : "secondary"
                      }
                      className="text-[10px]"
                    >
                      {doc.status}
                    </Badge>
                    <span>
                      {chunks.length} chunk{chunks.length === 1 ? "" : "s"}
                    </span>
                    {activeChunkId && (
                      <span className="text-ink">· highlighting source</span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {chunks.length === 0 ? (
              <p className="text-sm text-mute">
                {doc.status.toLowerCase() === "ready"
                  ? "No chunks found for this document."
                  : "Ingest this document to view indexed chunks."}
              </p>
            ) : (
              <ol className="space-y-3 pb-10">
                {chunks.map((chunk) => (
                  <ChunkCard
                    key={chunk.id}
                    chunk={chunk}
                    active={chunk.id === activeChunkId}
                    setActiveRef={
                      chunk.id === activeChunkId
                        ? (el) => {
                            activeRef.current = el;
                          }
                        : undefined
                    }
                  />
                ))}
              </ol>
            )}
          </>
        ) : null}
      </main>
    </div>
  );
}

function ChunkCard({
  chunk,
  active,
  setActiveRef,
}: {
  chunk: DocumentChunk;
  active: boolean;
  setActiveRef?: (el: HTMLElement | null) => void;
}) {
  return (
    <li
      ref={setActiveRef}
      id={`chunk-${chunk.id}`}
      className={cn(
        "scroll-mt-24 rounded-vercel-md border px-3 py-3 transition-shadow",
        active
          ? "border-ink/30 bg-canvas-soft ring-2 ring-ink/15"
          : "border-hairline bg-canvas",
      )}
    >
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
        <span className="font-semibold text-ink">
          Chunk {chunk.chunk_index + 1}
        </span>
        {typeof chunk.token_count === "number" && (
          <span className="text-mute">· ~{chunk.token_count} tokens</span>
        )}
        {active && (
          <Badge variant="success" className="text-[10px]">
            Cited
          </Badge>
        )}
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-body">
        {chunk.content}
      </p>
    </li>
  );
}
