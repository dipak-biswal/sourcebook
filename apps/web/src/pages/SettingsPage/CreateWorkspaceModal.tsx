import { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  FileUp,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import {
  api,
  type LearnCatalogResponse,
  type LearnChapter,
  type LearnTopic,
  type WorkspaceCurateResult,
  type WorkspaceCurateSource,
} from "@/api";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field-error";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { validateWorkspaceName } from "@/lib/validation";
import { formatError } from "@/lib/utils";

type Step = "form" | "curriculum";

const FILE_ACCEPT =
  ".txt,.md,.markdown,.pdf,.docx,.csv,.tsv,.json,.html,.htm,.rst,.xml,.yml,.yaml,.log";
const MAX_FILES = 10;

/** Same progress labels as Documents page ingest. */
const INGEST_STEPS = [
  "Starting ingest…",
  "Parsing document…",
  "Chunking text…",
  "Embedding chunks…",
  "Saving vectors…",
  "Almost done…",
];

type DocResult = {
  filename: string;
  status: "ready" | "failed" | "processing" | "error";
  error?: string;
};

async function sleep(ms: number) {
  await new Promise((r) => setTimeout(r, ms));
}

/**
 * Upload to storage (R2 when configured) then ingest — same API path as Documents.
 * Polls until ready / failed (background worker).
 */
async function uploadAndIngestFile(
  workspaceId: string,
  file: File,
  onProgress: (msg: string) => void,
): Promise<DocResult> {
  onProgress(`Uploading ${file.name}…`);
  let docId: string;
  try {
    const doc = await api.upload(workspaceId, file);
    docId = doc.id;
  } catch (e) {
    return {
      filename: file.name,
      status: "error",
      error: formatError(e),
    };
  }

  onProgress(`Starting ingest: ${file.name}…`);
  try {
    await api.ingestDocument(docId);
  } catch (e) {
    return {
      filename: file.name,
      status: "error",
      error: formatError(e),
    };
  }

  for (let i = 0; i < 40; i++) {
    onProgress(
      `${INGEST_STEPS[Math.min(i, INGEST_STEPS.length - 1)]} ${file.name}`,
    );
    await sleep(1500);
    try {
      const list = await api.documents(workspaceId);
      const d = list.find((x) => x.id === docId);
      const s = (d?.status || "").toLowerCase();
      if (s === "ready") {
        return { filename: file.name, status: "ready" };
      }
      if (s === "failed") {
        return {
          filename: file.name,
          status: "failed",
          error: d?.error || "Ingest failed",
        };
      }
      if (s === "uploaded") {
        // Ingest never started — retry once
        if (i === 2) {
          try {
            await api.ingestDocument(docId);
          } catch {
            /* keep polling */
          }
        }
      }
    } catch {
      /* keep polling */
    }
  }

  return {
    filename: file.name,
    status: "processing",
    error: "Ingest still running — check Documents if status stays processing.",
  };
}

function CurriculumPreview({ catalog }: { catalog: LearnCatalogResponse }) {
  const chapters: LearnChapter[] =
    catalog.chapters?.length
      ? catalog.chapters
      : (catalog.topics ?? [])
          .filter((t) => !t.parent_id)
          .map((t) => ({
            id: t.id,
            title: t.title,
            summary: t.summary,
            tags: t.tags,
            has_lesson: t.has_lesson,
            intro_id: t.id,
            children: (catalog.topics ?? []).filter((c) => c.parent_id === t.id),
          }));

  const [openId, setOpenId] = useState<string | null>(chapters[0]?.id ?? null);

  if (!chapters.length) {
    return (
      <p className="rounded-[8px] border border-dashed border-hairline px-3 py-6 text-center text-xs text-mute">
        No topics extracted from the sources.
      </p>
    );
  }

  return (
    <ul className="max-h-72 space-y-1 overflow-y-auto">
      {chapters.map((ch) => {
        const open = openId === ch.id;
        return (
          <li key={ch.id} className="rounded-[8px] border border-hairline bg-canvas">
            <button
              type="button"
              onClick={() => setOpenId(open ? null : ch.id)}
              className="flex w-full items-start gap-2 px-2.5 py-2 text-left"
            >
              {open ? (
                <ChevronDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mute" />
              ) : (
                <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mute" />
              )}
              <span className="min-w-0">
                <span className="block text-xs font-semibold text-ink">
                  {ch.title}
                </span>
                {ch.summary ? (
                  <span className="mt-0.5 block text-[11px] text-mute line-clamp-2">
                    {ch.summary}
                  </span>
                ) : null}
                <span className="mt-0.5 block text-[10px] text-mute">
                  Introduction
                  {ch.children.length
                    ? ` · ${ch.children.length} subtopic${ch.children.length === 1 ? "" : "s"}`
                    : ""}
                </span>
              </span>
            </button>
            {open ? (
              <ul className="space-y-0.5 border-t border-hairline px-2 py-1.5 pl-8">
                <li className="rounded-[6px] px-2 py-1 text-[11px] text-body">
                  Introduction
                </li>
                {ch.children.map((c: LearnTopic) => (
                  <li
                    key={c.id}
                    className="rounded-[6px] px-2 py-1 text-[11px] text-body"
                  >
                    <span className="font-medium text-ink">{c.title}</span>
                    {c.summary ? (
                      <span className="mt-0.5 block text-[10px] text-mute line-clamp-2">
                        {c.summary}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function SourceStatusList({ sources }: { sources: WorkspaceCurateSource[] }) {
  if (!sources.length) return null;
  return (
    <ul className="space-y-1 rounded-[8px] border border-hairline bg-canvas-soft/50 p-2">
      {sources.map((s) => (
        <li key={s.url} className="text-[11px] leading-snug">
          <span className={s.ok ? "text-emerald-700" : "text-red-600"}>
            {s.ok ? "✓" : "×"}
          </span>{" "}
          <span className="font-medium text-ink">
            {s.title || s.url}
          </span>
          {s.error ? (
            <span className="block text-mute">
              {typeof s.error === "string" ? s.error : "Fetch failed"}
            </span>
          ) : (
            <span className="block truncate text-mute">{s.url}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function CreateWorkspaceModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (workspaceId: string) => void;
}) {
  const { success, error: toastError } = useToast();
  const nameRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<Step>("form");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [urlDraft, setUrlDraft] = useState("");
  const [sourceUrls, setSourceUrls] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [tags, setTags] = useState<string[]>(["learning"]);
  const [nameError, setNameError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [curating, setCurating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [curatePreview, setCuratePreview] = useState<WorkspaceCurateResult | null>(
    null,
  );
  const [catalog, setCatalog] = useState<LearnCatalogResponse | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [docResults, setDocResults] = useState<DocResult[]>([]);

  const hasSources = sourceUrls.length > 0 || files.length > 0;
  const readyCount = docResults.filter((d) => d.status === "ready").length;

  useEffect(() => {
    if (!open) return;
    setStep("form");
    setName("");
    setDescription("");
    setUrlDraft("");
    setSourceUrls([]);
    setFiles([]);
    setTags(["learning"]);
    setNameError(null);
    setFormError(null);
    setCuratePreview(null);
    setCatalog(null);
    setCreatedId(null);
    setDocResults([]);
    setUploadStatus(null);
    setCurating(false);
    setSubmitting(false);
    requestAnimationFrame(() => nameRef.current?.focus());
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submitting && !curating) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose, submitting, curating]);

  if (!open) return null;

  function addUrl() {
    let u = urlDraft.trim();
    if (!u) return;
    if (!/^https?:\/\//i.test(u)) u = `https://${u}`;
    if (sourceUrls.includes(u)) {
      setUrlDraft("");
      return;
    }
    if (sourceUrls.length >= 12) {
      setFormError("Maximum 12 source URLs.");
      return;
    }
    setSourceUrls((prev) => [...prev, u]);
    setUrlDraft("");
    setFormError(null);
  }

  function removeUrl(u: string) {
    setSourceUrls((prev) => prev.filter((x) => x !== u));
    setCuratePreview(null);
  }

  function addFiles(list: FileList | null) {
    if (!list?.length) return;
    setFormError(null);
    setFiles((prev) => {
      const next = [...prev];
      for (const f of Array.from(list)) {
        if (next.length >= MAX_FILES) break;
        const dup = next.some(
          (x) => x.name === f.name && x.size === f.size && x.lastModified === f.lastModified,
        );
        if (!dup) next.push(f);
      }
      if (next.length >= MAX_FILES && list.length > 0) {
        setFormError(`Maximum ${MAX_FILES} files.`);
      }
      return next.slice(0, MAX_FILES);
    });
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleCurate() {
    const err = validateWorkspaceName(name);
    setNameError(err);
    if (err) return;
    if (!sourceUrls.length) {
      setFormError("Add at least one source URL to curate.");
      return;
    }
    setCurating(true);
    setFormError(null);
    try {
      const result = await api.workspaceCurateFromUrls(name.trim(), sourceUrls);
      setCuratePreview(result);
      if (result.description) setDescription(result.description);
      if (result.tags?.length) {
        setTags(
          result.tags.includes("learning")
            ? result.tags
            : ["learning", ...result.tags],
        );
      }
      if (result.ok_source_count === 0) {
        setFormError("None of the URLs could be fetched.");
        toastError("Curate failed", "No readable sources");
      } else {
        success(
          `Fetched ${result.ok_source_count} source(s) · ${result.topic_count} topics`,
        );
      }
    } catch (e) {
      const msg = formatError(e);
      setFormError(msg);
      toastError("Curate failed", msg);
    } finally {
      setCurating(false);
    }
  }

  async function handleCreate() {
    const err = validateWorkspaceName(name);
    setNameError(err);
    if (err) return;
    if (!sourceUrls.length && !files.length) {
      setFormError("Add at least one source URL or upload a file.");
      return;
    }

    setSubmitting(true);
    setFormError(null);
    setUploadStatus(null);
    try {
      const ws = await api.createWorkspace(name.trim());
      await api.updateWorkspace(ws.id, {
        description: description.trim() || null,
        tags: tags.length ? tags : ["learning"],
      });

      const results: DocResult[] = [];
      if (files.length) {
        for (let i = 0; i < files.length; i++) {
          const file = files[i];
          setUploadStatus(
            `Document ${i + 1}/${files.length}: ${file.name}`,
          );
          const result = await uploadAndIngestFile(
            ws.id,
            file,
            (msg) =>
              setUploadStatus(
                `Document ${i + 1}/${files.length}: ${msg}`,
              ),
          );
          results.push(result);
          if (result.status === "ready") {
            success("Document ready", file.name);
          } else if (result.status === "failed" || result.status === "error") {
            toastError(
              result.status === "error" ? "Upload failed" : "Ingest failed",
              `${file.name}: ${result.error || "Unknown error"}`,
            );
          } else {
            success(
              "Ingest still running",
              `${file.name} — check Documents if needed.`,
            );
          }
        }
        setDocResults(results);
      }

      let cat: LearnCatalogResponse | null = null;
      if (sourceUrls.length) {
        setUploadStatus("Building curriculum from URLs…");
        cat = await api.workspaceSetupCurriculum(ws.id, {
          name: name.trim(),
          description: description.trim() || null,
          tags: tags.length ? tags : ["learning"],
          source_urls: sourceUrls,
          docs_only: true,
        });
      }

      setCreatedId(ws.id);
      setCatalog(
        cat
          ? { ...cat, needs_setup: false, setup_hint: "" }
          : null,
      );
      setStep("curriculum");
      const nReady = results.filter((r) => r.status === "ready").length;
      success(
        nReady > 0 && sourceUrls.length
          ? `Workspace created · ${nReady} document(s) ready · curriculum ready`
          : nReady > 0
            ? `Workspace created · ${nReady} document(s) ready`
            : "Workspace created",
      );
      onCreated(ws.id);
    } catch (e) {
      const msg = formatError(e);
      setFormError(msg);
      toastError("Create failed", msg);
    } finally {
      setSubmitting(false);
      setUploadStatus(null);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4 backdrop-blur-[1px]">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-ws-title"
        className="flex max-h-[min(90vh,760px)] w-full max-w-lg flex-col overflow-hidden rounded-[12px] border border-hairline bg-canvas shadow-[var(--elevation-card)]"
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-hairline px-4 py-3">
          <div className="min-w-0">
            <h2
              id="create-ws-title"
              className="text-sm font-semibold text-ink"
            >
              {step === "form" ? "Add workspace" : "Curriculum ready"}
            </h2>
          </div>
          <button
            type="button"
            className="rounded p-1 text-mute hover:bg-canvas-soft hover:text-ink"
            aria-label="Close"
            disabled={submitting || curating}
            onClick={onClose}
          >
            <X className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {step === "form" ? (
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-mute">
                  Workspace name
                </label>
                <Input
                  ref={nameRef}
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setNameError(null);
                  }}
                  placeholder="e.g. System Design"
                  className="h-9 text-sm"
                  aria-invalid={!!nameError || undefined}
                  disabled={submitting || curating}
                />
                <FieldError error={nameError} />
              </div>

              <div>
                <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-mute">
                  Source URLs
                </label>
                <div className="flex gap-1">
                  <Input
                    value={urlDraft}
                    onChange={(e) => setUrlDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addUrl();
                      }
                    }}
                    placeholder="https://… (docs, TOC, guide)"
                    className="h-9 font-mono text-sm"
                    disabled={submitting || curating}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-9 shrink-0"
                    disabled={submitting || curating || !urlDraft.trim()}
                    onClick={addUrl}
                  >
                    <Plus className="h-3.5 w-3.5" strokeWidth={1.5} />
                    Add
                  </Button>
                </div>
                {sourceUrls.length > 0 ? (
                  <ul className="mt-2 space-y-1">
                    {sourceUrls.map((u) => (
                      <li
                        key={u}
                        className="flex items-center gap-2 rounded-[6px] border border-hairline bg-canvas-soft/40 px-2 py-1.5"
                      >
                        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-body">
                          {u}
                        </span>
                        <button
                          type="button"
                          className="rounded p-0.5 text-mute hover:text-red-600"
                          aria-label="Remove URL"
                          disabled={submitting || curating}
                          onClick={() => removeUrl(u)}
                        >
                          <Trash2 className="h-3 w-3" strokeWidth={1.5} />
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <label className="text-[11px] font-medium uppercase tracking-wide text-mute">
                    Documents
                  </label>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-7 gap-1 text-[11px]"
                    disabled={
                      submitting || curating || files.length >= MAX_FILES
                    }
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <FileUp className="h-3 w-3" strokeWidth={1.5} />
                    Upload files
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    className="hidden"
                    accept={FILE_ACCEPT}
                    multiple
                    disabled={submitting || curating}
                    onChange={(e) => {
                      addFiles(e.target.files);
                      e.target.value = "";
                    }}
                  />
                </div>
                <p className="text-[10px] text-mute">
                  PDF, DOCX, Markdown, text, and similar. On create each file is
                  uploaded and ingested (same as Documents).
                </p>
                {files.length > 0 ? (
                  <ul className="mt-2 space-y-1">
                    {files.map((f, i) => (
                      <li
                        key={`${f.name}-${f.size}-${f.lastModified}`}
                        className="flex items-center gap-2 rounded-[6px] border border-hairline bg-canvas-soft/40 px-2 py-1.5"
                      >
                        <FileUp
                          className="h-3 w-3 shrink-0 text-mute"
                          strokeWidth={1.5}
                        />
                        <span className="min-w-0 flex-1 truncate text-[11px] text-body">
                          {f.name}
                          <span className="text-mute">
                            {" "}
                            · {(f.size / 1024).toFixed(0)} KB
                          </span>
                        </span>
                        <button
                          type="button"
                          className="rounded p-0.5 text-mute hover:text-red-600"
                          aria-label={`Remove ${f.name}`}
                          disabled={submitting || curating}
                          onClick={() => removeFile(i)}
                        >
                          <Trash2 className="h-3 w-3" strokeWidth={1.5} />
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <label className="text-[11px] font-medium uppercase tracking-wide text-mute">
                    Description
                  </label>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-7 text-[11px]"
                    disabled={
                      curating ||
                      submitting ||
                      name.trim().length < 2 ||
                      sourceUrls.length === 0
                    }
                    onClick={() => void handleCurate()}
                  >
                    {curating ? (
                      <>
                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        Fetching URLs…
                      </>
                    ) : (
                      <>
                        <Sparkles className="mr-1 h-3 w-3" strokeWidth={1.5} />
                        Curate from URLs
                      </>
                    )}
                  </Button>
                </div>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={4}
                  disabled={submitting || curating}
                  className="w-full resize-y rounded-[8px] border border-hairline bg-canvas px-3 py-2 text-sm text-ink outline-none focus:border-ink/30 disabled:opacity-60"
                  placeholder="Optional description"
                />
                {curatePreview ? (
                  <div className="mt-2 space-y-1.5">
                    <p className="text-[10px] text-mute">
                      {curatePreview.ok_source_count}/
                      {curatePreview.sources.length} sources ·{" "}
                      {curatePreview.topic_count} topics
                    </p>
                    <SourceStatusList sources={curatePreview.sources} />
                  </div>
                ) : null}
              </div>

              {uploadStatus ? (
                <p className="flex items-center gap-1.5 text-[11px] text-mute">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  {uploadStatus}
                </p>
              ) : null}

              {formError ? (
                <p className="text-xs text-red-600">{formError}</p>
              ) : null}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs text-ink">
                <BookOpen className="h-4 w-4 text-mute" strokeWidth={1.5} />
                <span className="font-semibold">{name.trim()}</span>
                {catalog?.chapters?.length || catalog?.topics?.length ? (
                  <span className="text-mute">
                    ·{" "}
                    {(catalog.chapters?.length ||
                      catalog.topics.filter((t) => !t.parent_id).length) ??
                      0}{" "}
                    chapters
                  </span>
                ) : null}
                {docResults.length > 0 ? (
                  <span className="text-mute">
                    · {readyCount}/{docResults.length} docs ready
                  </span>
                ) : null}
              </div>

              {docResults.length > 0 ? (
                <ul className="space-y-1 rounded-[8px] border border-hairline bg-canvas-soft/40 p-2">
                  {docResults.map((d) => (
                    <li
                      key={d.filename}
                      className="flex items-start gap-2 text-[11px] leading-snug"
                    >
                      <span
                        className={
                          d.status === "ready"
                            ? "text-emerald-700"
                            : d.status === "processing"
                              ? "text-amber-700"
                              : "text-red-600"
                        }
                      >
                        {d.status === "ready"
                          ? "✓"
                          : d.status === "processing"
                            ? "…"
                            : "×"}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="font-medium text-ink">{d.filename}</span>
                        <span className="text-mute"> · {d.status}</span>
                        {d.error ? (
                          <span className="block text-mute">{d.error}</span>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}

              {catalog?.sources?.length ? (
                <SourceStatusList sources={catalog.sources} />
              ) : null}
              {catalog ? (
                <CurriculumPreview catalog={catalog} />
              ) : (
                <p className="rounded-[8px] border border-dashed border-hairline px-3 py-6 text-center text-xs text-mute">
                  {readyCount > 0
                    ? "Documents are ready for chat and agents. Open Documents anytime to manage them."
                    : docResults.length > 0
                      ? "Some documents are still processing or failed. Open Documents to retry ingest."
                      : "Workspace ready."}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex shrink-0 justify-end gap-2 border-t border-hairline px-4 py-3">
          {step === "form" ? (
            <>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={submitting || curating}
                onClick={onClose}
              >
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={
                  submitting ||
                  curating ||
                  !name.trim() ||
                  !hasSources
                }
                onClick={() => void handleCreate()}
              >
                {submitting ? (
                  <>
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    Creating…
                  </>
                ) : (
                  "Create workspace"
                )}
              </Button>
            </>
          ) : (
            <Button
              type="button"
              size="sm"
              onClick={() => {
                if (createdId) onCreated(createdId);
                onClose();
              }}
            >
              Done
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
