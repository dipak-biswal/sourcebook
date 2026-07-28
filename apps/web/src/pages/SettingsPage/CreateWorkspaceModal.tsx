import { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import {
  api,
  type LearnCatalogResponse,
  type LearnChapter,
  type LearnTopic,
} from "@/api";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field-error";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { validateWorkspaceName } from "@/lib/validation";
import { formatError } from "@/lib/utils";

type Step = "form" | "curriculum";

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
        No curriculum topics were extracted from the documentation. Check the
        docs URL or try another page (e.g. a table of contents / index).
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

  const [step, setStep] = useState<Step>("form");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [docsUrl, setDocsUrl] = useState("");
  const [tags, setTags] = useState<string[]>(["learning"]);
  const [nameError, setNameError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [curating, setCurating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [catalog, setCatalog] = useState<LearnCatalogResponse | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setStep("form");
    setName("");
    setDescription("");
    setDocsUrl("");
    setTags(["learning"]);
    setNameError(null);
    setFormError(null);
    setCatalog(null);
    setCreatedId(null);
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

  async function handleCurate() {
    const err = validateWorkspaceName(name);
    setNameError(err);
    if (err) return;
    setCurating(true);
    setFormError(null);
    try {
      const s = await api.workspaceSuggestDescription(name.trim());
      if (s.description) setDescription(s.description);
      if (s.suggested_docs_url && !docsUrl.trim()) {
        setDocsUrl(s.suggested_docs_url);
      }
      if (s.tags?.length) {
        setTags(
          s.tags.includes("learning") ? s.tags : ["learning", ...s.tags],
        );
      }
      success("Description curated from web search");
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

    const url = docsUrl.trim();
    setSubmitting(true);
    setFormError(null);
    try {
      const ws = await api.createWorkspace(name.trim());
      await api.updateWorkspace(ws.id, {
        description: description.trim() || null,
        tags: tags.length ? tags : ["learning"],
      });

      let cat: LearnCatalogResponse | null = null;
      if (url) {
        cat = await api.workspaceSetupCurriculum(ws.id, {
          name: name.trim(),
          description: description.trim() || null,
          tags: tags.length ? tags : ["learning"],
          docs_url: url,
          docs_only: true,
        });
      } else {
        // No docs URL: create workspace only (no invented curriculum).
        cat = {
          workspace_id: ws.id,
          domain: name.trim(),
          needs_setup: false,
          setup_hint: "",
          source: "",
          docs_url: "",
          topics: [],
          chapters: [],
        };
      }

      setCreatedId(ws.id);
      setCatalog(cat);
      setStep("curriculum");
      success(
        url
          ? `Workspace created · curriculum from documentation`
          : `Workspace "${name.trim()}" created`,
      );
      onCreated(ws.id);
    } catch (e) {
      const msg = formatError(e);
      setFormError(msg);
      toastError("Create failed", msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4 backdrop-blur-[1px]">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-ws-title"
        className="flex max-h-[min(90vh,720px)] w-full max-w-lg flex-col overflow-hidden rounded-[12px] border border-hairline bg-canvas shadow-[var(--elevation-card)]"
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-hairline px-4 py-3">
          <div className="min-w-0">
            <h2
              id="create-ws-title"
              className="text-sm font-semibold text-ink"
            >
              {step === "form" ? "Add workspace" : "Curriculum"}
            </h2>
            <p className="mt-0.5 text-[11px] text-mute">
              {step === "form"
                ? "Name the workspace, curate a description, and optionally point at official docs to build the topic tree."
                : catalog?.docs_url
                  ? `Extracted from documentation (${catalog.source || "docs"}).`
                  : "Workspace ready. Add a docs URL later to fetch curriculum."}
            </p>
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
                  placeholder="e.g. Python"
                  className="h-9 text-sm"
                  aria-invalid={!!nameError || undefined}
                  disabled={submitting || curating}
                />
                <FieldError error={nameError} />
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
                    disabled={curating || submitting || name.trim().length < 2}
                    onClick={() => void handleCurate()}
                  >
                    {curating ? (
                      <>
                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        Curating…
                      </>
                    ) : (
                      <>
                        <Sparkles className="mr-1 h-3 w-3" strokeWidth={1.5} />
                        Curate description
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
                  placeholder="Click “Curate description” to fill from web search, or write your own…"
                />
              </div>

              <div>
                <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-mute">
                  Documentation URL{" "}
                  <span className="font-normal normal-case text-mute">
                    (optional)
                  </span>
                </label>
                <Input
                  value={docsUrl}
                  onChange={(e) => setDocsUrl(e.target.value)}
                  placeholder="https://docs.python.org/3/"
                  className="h-9 font-mono text-sm"
                  disabled={submitting || curating}
                />
                <p className="mt-1 text-[11px] text-mute">
                  When set, curriculum topics are fetched from this documentation
                  only (page + same-site TOC), not generic web inventing.
                </p>
              </div>

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
              </div>
              {catalog ? <CurriculumPreview catalog={catalog} /> : null}
              {!docsUrl.trim() ? (
                <p className="text-[11px] text-mute">
                  No docs URL was provided, so no curriculum was fetched. You can
                  open Learn later and add a documentation source.
                </p>
              ) : null}
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
                disabled={submitting || curating || !name.trim()}
                onClick={() => void handleCreate()}
              >
                {submitting ? (
                  <>
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    {docsUrl.trim()
                      ? "Creating & fetching curriculum…"
                      : "Creating…"}
                  </>
                ) : docsUrl.trim() ? (
                  "Create & fetch curriculum"
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
