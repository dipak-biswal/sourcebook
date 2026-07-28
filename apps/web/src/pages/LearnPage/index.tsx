import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  GraduationCap,
  Loader2,
  PanelLeft,
  PanelRight,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type LearnCatalogResponse,
  type LearnChapter,
  type LearnLesson,
  type LearnTopic,
  type Workspace,
} from "@/api";
import { AppHeader } from "@/components/layout/AppHeader";
import { WorkspaceSelect } from "@/components/workspace/WorkspaceSelect";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { GenerativeUIView } from "@/components/agents/GenerativeUI";
import type { GenerativeUIPayload } from "@/components/agents/generative-ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorAlert } from "@/components/ui/error-alert";
import { Sheet } from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { useWorkspaces } from "@/hooks/queries";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useLastWorkspace } from "@/hooks/useLastWorkspace";
import {
  parseTagInput,
  SUGGESTED_WORKSPACE_TAGS,
  toggleTagInInput,
  WORKSPACE_DESCRIPTION_TEMPLATE,
} from "@/pages/SettingsPage/workspace-tags";
import { validateWorkspaceName } from "@/lib/validation";
import { cn, formatError } from "@/lib/utils";
import { setToken } from "@/api";

function lessonToVisualPayload(lesson: LearnLesson): GenerativeUIPayload | null {
  const blocks = (lesson.visuals ?? []).map((v) => {
    // Diagram blocks need nodes/paths; fall back to scannable lists when LLM
    // only returned pipe/bullet items.
    let type = v.type;
    if (
      (type === "flow_diagram" ||
        type === "sequence_diagram" ||
        type === "compare_paths") &&
      (v.items?.length ?? 0) > 0
    ) {
      type = type === "compare_paths" ? "comparison" : "steps";
    }
    return {
      type,
      title: v.title,
      body: v.body ?? null,
      items: v.items ?? null,
      width: (v.width as "full" | "half") || "full",
      tags: [`__visual:${v.id}`],
    };
  });
  if (!blocks.length) return null;
  return {
    type: "generative_ui",
    title: `${lesson.title} — figures`,
    plain_summary: lesson.summary || "",
    presentation_profile: "learn_visuals",
    blocks,
  };
}

function WorkspaceSetupPanel({
  workspaces,
  workspaceId,
  onWorkspaceChange,
  onRefreshWorkspaces,
  onSaved,
}: {
  workspaces: Workspace[];
  workspaceId: string;
  onWorkspaceChange: (id: string) => void;
  onRefreshWorkspaces: () => void;
  onSaved: () => void;
}) {
  const { success, error: toastError } = useToast();
  const existing = workspaces.find((w) => w.id === workspaceId);
  const [name, setName] = useState(existing?.name ?? "");
  const [description, setDescription] = useState(
    existing?.description ?? WORKSPACE_DESCRIPTION_TEMPLATE,
  );
  const [tagsInput, setTagsInput] = useState(
    (existing?.tags ?? ["learning"]).join(", "),
  );
  const [saving, setSaving] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);

  useEffect(() => {
    setName(existing?.name ?? "");
    setDescription(existing?.description ?? WORKSPACE_DESCRIPTION_TEMPLATE);
    setTagsInput((existing?.tags ?? ["learning"]).join(", "));
  }, [existing?.id, existing?.name, existing?.description, existing?.tags]);

  async function handleSave() {
    const err = validateWorkspaceName(name);
    setNameError(err);
    if (err) return;
    setSaving(true);
    try {
      const tags = parseTagInput(tagsInput);
      if (!tags.includes("learning")) tags.push("learning");
      if (!workspaceId || !existing) {
        const ws = await api.createWorkspace(name.trim());
        await api.updateWorkspace(ws.id, {
          description: description.trim() || null,
          tags,
        });
        onRefreshWorkspaces();
        onWorkspaceChange(ws.id);
        success("Workspace ready for Learn");
      } else {
        await api.updateWorkspace(workspaceId, {
          name: name.trim(),
          description: description.trim() || null,
          tags,
        });
        onRefreshWorkspaces();
        success("Workspace details saved");
      }
      onSaved();
    } catch (e) {
      toastError("Could not save workspace", formatError(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-10">
      <div className="mb-6 flex items-start gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-[10px] border border-hairline bg-canvas-soft">
          <GraduationCap className="h-5 w-5 text-ink" strokeWidth={1.5} />
        </div>
        <div>
          <h1 className="text-lg font-semibold text-ink">Set up Learn</h1>
          <p className="mt-1 text-sm text-mute">
            Tell us what this workspace is for. We use the name, description,
            and tags to fetch a relevant topic catalog — like chapters in a
            visual textbook.
          </p>
        </div>
      </div>

      {workspaces.length > 0 && (
        <div className="mb-4">
          <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-mute">
            Workspace
          </label>
          <WorkspaceSelect
            workspaces={workspaces}
            workspaceId={workspaceId}
            onChange={onWorkspaceChange}
            onRefresh={onRefreshWorkspaces}
          />
        </div>
      )}

      <div className="space-y-3 rounded-[12px] border border-hairline bg-canvas p-4">
        <div>
          <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-mute">
            Name
          </label>
          <Input
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setNameError(null);
            }}
            placeholder="e.g. ML fundamentals"
            className="h-9 text-sm"
            aria-invalid={!!nameError || undefined}
          />
          {nameError && (
            <p className="mt-1 text-xs text-red-600">{nameError}</p>
          )}
        </div>
        <div>
          <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-mute">
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={5}
            className="w-full resize-y rounded-[8px] border border-hairline bg-canvas px-3 py-2 text-sm text-ink outline-none focus:border-ink/30"
            placeholder="What do you want to learn?"
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-mute">
            Tags
          </label>
          <Input
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="learning, system-design, ML"
            className="h-9 text-sm"
          />
          <div className="mt-2 flex flex-wrap gap-1.5">
            {SUGGESTED_WORKSPACE_TAGS.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => setTagsInput((cur) => toggleTagInInput(cur, tag))}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-[11px]",
                  parseTagInput(tagsInput).includes(tag)
                    ? "border-ink bg-ink text-[var(--canvas)]"
                    : "border-hairline bg-canvas-soft text-mute hover:text-ink",
                )}
              >
                {tag}
              </button>
            ))}
          </div>
        </div>
        <Button
          type="button"
          className="w-full"
          disabled={saving}
          onClick={() => void handleSave()}
        >
          {saving ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Saving…
            </>
          ) : (
            "Continue to topics"
          )}
        </Button>
      </div>
    </div>
  );
}

function chaptersFromCatalog(catalog: LearnCatalogResponse): LearnChapter[] {
  if (catalog.chapters?.length) return catalog.chapters;
  // Legacy flat catalog: each root topic is its own chapter.
  return (catalog.topics ?? [])
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
}

function TopicSidebar({
  catalog,
  selectedId,
  expandedChapterId,
  onExpandChapter,
  onSelect,
  onRefresh,
  refreshing,
  lesson,
  activeSectionId,
  onJump,
}: {
  catalog: LearnCatalogResponse;
  selectedId: string | null;
  expandedChapterId: string | null;
  onExpandChapter: (id: string) => void;
  onSelect: (id: string) => void;
  onRefresh: () => void;
  refreshing: boolean;
  lesson: LearnLesson | null;
  activeSectionId: string | null;
  onJump: (id: string) => void;
}) {
  const chapters = chaptersFromCatalog(catalog);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-hairline px-3 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="text-[10px] font-bold uppercase tracking-wide text-mute">
              Topics
            </div>
            <div className="truncate text-sm font-semibold text-ink">
              {catalog.domain || "Learning path"}
            </div>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            aria-label="Refresh topics"
            disabled={refreshing}
            onClick={onRefresh}
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", refreshing && "animate-spin")}
              strokeWidth={1.5}
            />
          </Button>
        </div>
        {catalog.source && (
          <p className="mt-1 text-[10px] text-mute">
            Source: {catalog.source} · expand a chapter for subtopics
          </p>
        )}
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto p-2">
        {chapters.map((ch) => {
          const expanded = ch.id === expandedChapterId;
          const chapterSelected =
            selectedId === ch.intro_id ||
            ch.children.some((c) => c.id === selectedId);
          return (
            <li key={ch.id} className="mb-1">
              <button
                type="button"
                onClick={() => {
                  onExpandChapter(ch.id);
                  // Opening a chapter selects its Introduction lesson.
                  onSelect(ch.intro_id);
                }}
                className={cn(
                  "flex w-full items-start gap-1.5 rounded-[8px] px-2 py-2 text-left transition-colors",
                  chapterSelected && expanded
                    ? "bg-canvas-soft-2"
                    : "hover:bg-canvas-soft",
                )}
                aria-expanded={expanded}
              >
                <span className="mt-0.5 shrink-0 text-mute">
                  {expanded ? (
                    <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.75} />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.75} />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-xs font-semibold leading-snug text-ink">
                    {ch.title}
                  </span>
                  {ch.summary && !expanded && (
                    <span className="mt-0.5 block line-clamp-2 text-[11px] leading-snug text-mute">
                      {ch.summary}
                    </span>
                  )}
                  {ch.children.length > 0 && (
                    <span className="mt-0.5 block text-[10px] text-mute">
                      {ch.children.length} subtopic
                      {ch.children.length === 1 ? "" : "s"}
                    </span>
                  )}
                </span>
              </button>

              {expanded && (
                <ul className="ml-3 mt-0.5 space-y-0.5 border-l border-hairline pl-2">
                  <li>
                    <button
                      type="button"
                      onClick={() => onSelect(ch.intro_id)}
                      className={cn(
                        "w-full rounded-[6px] px-2 py-1.5 text-left text-[11px] leading-snug transition-colors",
                        selectedId === ch.intro_id
                          ? "bg-ink font-semibold text-[var(--canvas)]"
                          : "text-body hover:bg-canvas-soft",
                      )}
                    >
                      Introduction
                      {ch.summary ? (
                        <span
                          className={cn(
                            "mt-0.5 block line-clamp-2 text-[10px] font-normal",
                            selectedId === ch.intro_id
                              ? "text-[var(--canvas)]/75"
                              : "text-mute",
                          )}
                        >
                          {ch.summary}
                        </span>
                      ) : null}
                    </button>
                  </li>
                  {ch.children.map((child: LearnTopic) => {
                    const active = child.id === selectedId;
                    return (
                      <li key={child.id}>
                        <button
                          type="button"
                          onClick={() => onSelect(child.id)}
                          className={cn(
                            "w-full rounded-[6px] px-2 py-1.5 text-left text-[11px] leading-snug transition-colors",
                            active
                              ? "bg-ink font-semibold text-[var(--canvas)]"
                              : "text-body hover:bg-canvas-soft",
                          )}
                        >
                          {child.title}
                          {child.summary ? (
                            <span
                              className={cn(
                                "mt-0.5 block line-clamp-2 text-[10px] font-normal",
                                active
                                  ? "text-[var(--canvas)]/75"
                                  : "text-mute",
                              )}
                            >
                              {child.summary}
                            </span>
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
        {chapters.length === 0 && (
          <li className="px-2 py-6 text-center text-xs text-mute">
            No topics yet. Refresh after saving workspace details.
          </li>
        )}
      </ul>
      {lesson && (
        <div className="max-h-[38%] shrink-0 overflow-y-auto border-t border-hairline">
          <LessonDetailsSidebar
            lesson={lesson}
            activeSectionId={activeSectionId}
            onJump={onJump}
          />
        </div>
      )}
    </div>
  );
}

function LessonDetailsSidebar({
  lesson,
  activeSectionId,
  onJump,
}: {
  lesson: LearnLesson;
  activeSectionId: string | null;
  onJump: (id: string) => void;
}) {
  return (
    <div className="space-y-4 p-3">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-wide text-mute">
          On this page
        </div>
        <ul className="mt-2 space-y-0.5">
          {lesson.outline.map((o) => (
            <li key={o.id}>
              <button
                type="button"
                onClick={() => onJump(o.id)}
                className={cn(
                  "w-full rounded-[6px] px-2 py-1.5 text-left text-[11px] leading-snug",
                  activeSectionId === o.id
                    ? "bg-emerald-500/10 font-semibold text-emerald-800 dark:text-emerald-300"
                    : "text-body hover:bg-canvas-soft",
                )}
              >
                {o.heading}
              </button>
            </li>
          ))}
        </ul>
      </div>
      {lesson.prerequisites.length > 0 && (
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide text-mute">
            Prerequisites
          </div>
          <ul className="mt-1.5 list-disc space-y-1 pl-4 text-[11px] text-body">
            {lesson.prerequisites.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      {lesson.key_terms.length > 0 && (
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide text-mute">
            Key terms
          </div>
          <dl className="mt-1.5 space-y-2">
            {lesson.key_terms.map((kt) => (
              <div key={kt.term}>
                <dt className="text-[11px] font-semibold text-ink">{kt.term}</dt>
                <dd className="text-[11px] leading-snug text-mute">
                  {kt.definition}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

function LessonMiddle({
  lesson,
  loading,
  onRefresh,
  refreshing,
}: {
  lesson: LearnLesson | null;
  loading: boolean;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  if (loading) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-16 text-mute">
        <Loader2 className="h-6 w-6 animate-spin" />
        <p className="text-sm">Generating lesson…</p>
        <p className="max-w-sm text-center text-xs">
          Writing a detailed chapter with sections and figures for this topic.
        </p>
      </div>
    );
  }
  if (!lesson) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 py-16 text-center">
        <BookOpen className="h-8 w-8 text-mute" strokeWidth={1.25} />
        <p className="text-sm font-medium text-ink">Pick a topic</p>
        <p className="max-w-sm text-xs text-mute">
          Choose a chapter from the left. We open a full lesson with prose in
          the center and diagrams on the right.
        </p>
      </div>
    );
  }

  return (
    <article className="mx-auto max-w-2xl px-4 py-6 sm:px-6 sm:py-8">
      <header className="mb-6 border-b border-hairline pb-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-wide text-mute">
              Lesson
              {lesson.cached ? " · cached" : ""}
              {lesson.fallback ? " · offline fallback" : ""}
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">
              {lesson.title}
            </h1>
            {lesson.summary && (
              <p className="mt-2 text-sm leading-relaxed text-body">
                {lesson.summary}
              </p>
            )}
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="shrink-0"
            disabled={refreshing}
            onClick={onRefresh}
          >
            {refreshing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
            <span className="ml-1.5">Regenerate</span>
          </Button>
        </div>
      </header>

      <div className="space-y-10">
        {lesson.sections.map((sec, i) => (
          <section
            key={sec.id}
            id={`learn-sec-${sec.id}`}
            className="scroll-mt-20"
          >
            <h2 className="mb-3 flex items-baseline gap-2 text-lg font-semibold text-ink">
              <span className="font-mono text-sm text-mute">
                {String(i + 1).padStart(2, "0")}
              </span>
              {sec.heading}
            </h2>
            <MarkdownContent
              content={sec.body_md}
              className="prose-sm max-w-none text-body"
            />
          </section>
        ))}
      </div>
    </article>
  );
}

function VisualsPanel({ lesson }: { lesson: LearnLesson | null }) {
  const payload = useMemo(
    () => (lesson ? lessonToVisualPayload(lesson) : null),
    [lesson],
  );

  if (!lesson) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-mute">
        <Sparkles className="h-6 w-6" strokeWidth={1.25} />
        <p className="text-xs">Figures appear here when a lesson is open.</p>
      </div>
    );
  }
  if (!payload) {
    return (
      <div className="p-4 text-xs text-mute">
        No figures for this lesson yet. Regenerate to request diagrams.
      </div>
    );
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-3">
      <div className="mb-2 text-[10px] font-bold uppercase tracking-wide text-mute">
        Visuals
      </div>
      <GenerativeUIView payload={payload} />
    </div>
  );
}

function LearnPageInner() {
  const queryClient = useQueryClient();
  const { data: workspaces = [], isLoading: wsLoading, refetch: refetchWs } =
    useWorkspaces();
  const { workspaceId, setWorkspaceId } = useLastWorkspace(workspaces);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [expandedChapterId, setExpandedChapterId] = useState<string | null>(
    null,
  );
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topicsRefreshing, setTopicsRefreshing] = useState(false);
  const [lessonRefreshing, setLessonRefreshing] = useState(false);

  useDocumentTitle("Learn");

  const catalogQuery = useQuery({
    queryKey: ["learnTopics", workspaceId],
    queryFn: () => api.learnTopics(workspaceId!, false),
    enabled: !!workspaceId,
    staleTime: 60_000,
  });

  const catalog = catalogQuery.data;
  const needsSetup =
    !workspaceId ||
    workspaces.length === 0 ||
    catalog?.needs_setup === true;

  useEffect(() => {
    if (!catalog) return;
    const chapters = chaptersFromCatalog(catalog);
    if (!chapters.length) return;

    const topicExists =
      selectedTopicId &&
      catalog.topics.some((t) => t.id === selectedTopicId);

    if (topicExists && selectedTopicId) {
      // Keep expanded chapter in sync with selection.
      const parent =
        catalog.topics.find((t) => t.id === selectedTopicId)?.parent_id ||
        chapters.find(
          (c) =>
            c.intro_id === selectedTopicId ||
            c.children.some((ch) => ch.id === selectedTopicId),
        )?.id;
      if (parent && parent !== expandedChapterId) {
        setExpandedChapterId(parent);
      }
      return;
    }

    const preferred = catalog.last_selected_topic_id
      ? catalog.topics.find((t) => t.id === catalog.last_selected_topic_id)
      : undefined;
    const nextId = preferred?.id ?? chapters[0]?.intro_id ?? null;
    setSelectedTopicId(nextId);
    if (preferred?.parent_id) {
      setExpandedChapterId(preferred.parent_id);
    } else if (nextId) {
      const ch =
        chapters.find((c) => c.intro_id === nextId || c.id === nextId) ??
        chapters[0];
      setExpandedChapterId(ch?.id ?? null);
    }
  }, [catalog, selectedTopicId, expandedChapterId]);

  const lessonQuery = useQuery({
    queryKey: ["learnLesson", workspaceId, selectedTopicId],
    queryFn: () => api.learnLesson(workspaceId!, selectedTopicId!, false),
    enabled: !!workspaceId && !!selectedTopicId && !needsSetup,
    staleTime: 5 * 60_000,
  });

  const handleRefreshTopics = useCallback(async () => {
    if (!workspaceId) return;
    setTopicsRefreshing(true);
    try {
      const data = await api.learnTopics(workspaceId, true);
      queryClient.setQueryData(["learnTopics", workspaceId], data);
    } catch (e) {
      setError(formatError(e));
    } finally {
      setTopicsRefreshing(false);
    }
  }, [workspaceId, queryClient]);

  const handleRefreshLesson = useCallback(async () => {
    if (!workspaceId || !selectedTopicId) return;
    setLessonRefreshing(true);
    try {
      const data = await api.learnLesson(workspaceId, selectedTopicId, true);
      queryClient.setQueryData(
        ["learnLesson", workspaceId, selectedTopicId],
        data,
      );
    } catch (e) {
      setError(formatError(e));
    } finally {
      setLessonRefreshing(false);
    }
  }, [workspaceId, selectedTopicId, queryClient]);

  useEffect(() => {
    if (catalogQuery.error) {
      setError(formatError(catalogQuery.error));
    } else if (lessonQuery.error) {
      setError(formatError(lessonQuery.error));
    } else {
      setError(null);
    }
  }, [catalogQuery.error, lessonQuery.error]);

  const lesson = lessonQuery.data ?? null;

  const jumpToSection = useCallback((id: string) => {
    setActiveSectionId(id);
    const el = document.getElementById(`learn-sec-${id}`);
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  function handleLogout() {
    setToken(null);
    window.location.href = "/login";
  }

  const showReader = !needsSetup && !!catalog && !catalog.needs_setup;

  return (
    <div className="app-shell">
      <AppHeader onLogout={handleLogout} />

      <div className="flex shrink-0 items-center gap-2 border-b border-hairline bg-canvas px-3 py-2 sm:px-4">
        <GraduationCap className="hidden h-4 w-4 text-mute sm:block" strokeWidth={1.5} />
        <span className="text-sm font-semibold text-ink">Learn</span>
        <div className="ml-auto flex min-w-0 items-center gap-2">
          {workspaces.length > 0 && workspaceId && (
            <WorkspaceSelect
              workspaces={workspaces}
              workspaceId={workspaceId}
              onChange={setWorkspaceId}
              onRefresh={() => void refetchWs()}
            />
          )}
        </div>
      </div>

      {wsLoading ? (
        <div className="flex flex-1 items-center justify-center text-mute">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : needsSetup ? (
        <main id="main-content" tabIndex={-1} className="document-scroll flex-1 overflow-y-auto">
          {error && (
            <div className="mx-auto max-w-lg px-4 pt-4">
              <ErrorAlert message={error} onDismiss={() => setError(null)} />
            </div>
          )}
          {catalog?.setup_hint && workspaceId && (
            <p className="mx-auto max-w-lg px-4 pt-4 text-xs text-amber-800 dark:text-amber-200">
              {catalog.setup_hint}
            </p>
          )}
          <WorkspaceSetupPanel
            workspaces={workspaces}
            workspaceId={workspaceId}
            onWorkspaceChange={setWorkspaceId}
            onRefreshWorkspaces={() => void refetchWs()}
            onSaved={() => {
              void queryClient.invalidateQueries({
                queryKey: ["learnTopics"],
              });
            }}
          />
        </main>
      ) : catalogQuery.isLoading || !catalog ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 text-mute">
          <Loader2 className="h-5 w-5 animate-spin" />
          <p className="text-sm">Loading topics for this workspace…</p>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          {/* Left: topics + lesson meta */}
          <aside className="hidden w-72 shrink-0 flex-col border-r border-hairline bg-canvas lg:flex">
            {catalog && (
              <TopicSidebar
                catalog={catalog}
                selectedId={selectedTopicId}
                expandedChapterId={expandedChapterId}
                onExpandChapter={setExpandedChapterId}
                onSelect={setSelectedTopicId}
                onRefresh={() => void handleRefreshTopics()}
                refreshing={topicsRefreshing || catalogQuery.isFetching}
                lesson={lessonQuery.isLoading ? null : lesson}
                activeSectionId={activeSectionId}
                onJump={jumpToSection}
              />
            )}
          </aside>

          <Sheet
            open={leftOpen}
            onClose={() => setLeftOpen(false)}
            title="Topics"
            side="left"
            mobileOnly={false}
          >
            {catalog && (
              <TopicSidebar
                catalog={catalog}
                selectedId={selectedTopicId}
                expandedChapterId={expandedChapterId}
                onExpandChapter={setExpandedChapterId}
                onSelect={(id) => {
                  setSelectedTopicId(id);
                  setLeftOpen(false);
                }}
                onRefresh={() => void handleRefreshTopics()}
                refreshing={topicsRefreshing || catalogQuery.isFetching}
                lesson={lessonQuery.isLoading ? null : lesson}
                activeSectionId={activeSectionId}
                onJump={(id) => {
                  jumpToSection(id);
                  setLeftOpen(false);
                }}
              />
            )}
          </Sheet>

          {/* Middle: detailed lesson */}
          <main
            id="main-content"
            tabIndex={-1}
            className="document-scroll flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto outline-none"
          >
            <div className="flex shrink-0 items-center gap-2 border-b border-hairline px-3 py-2 lg:hidden">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Open topics"
                onClick={() => setLeftOpen(true)}
              >
                <PanelLeft className="h-4 w-4" strokeWidth={1.5} />
              </Button>
              <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">
                {lesson?.title || catalog?.domain || "Learn"}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Open visuals"
                onClick={() => setRightOpen(true)}
              >
                <PanelRight className="h-4 w-4" strokeWidth={1.5} />
              </Button>
            </div>

            {error && (
              <div className="px-4 pt-3">
                <ErrorAlert
                  message={error}
                  onDismiss={() => setError(null)}
                  onRetry={() => void lessonQuery.refetch()}
                />
              </div>
            )}

            {showReader && (
              <LessonMiddle
                lesson={lesson}
                loading={
                  !!selectedTopicId && lessonQuery.isFetching && !lesson
                }
                onRefresh={() => void handleRefreshLesson()}
                refreshing={lessonRefreshing}
              />
            )}
          </main>

          {/* Right: diagrams / GenUI */}
          <aside className="hidden w-80 shrink-0 flex-col border-l border-hairline bg-canvas-soft xl:flex 2xl:w-[22rem]">
            <VisualsPanel
              lesson={
                lessonQuery.isFetching && !lesson ? null : lesson
              }
            />
          </aside>

          <Sheet
            open={rightOpen}
            onClose={() => setRightOpen(false)}
            title="Visuals"
            side="right"
            mobileOnly={false}
          >
            <VisualsPanel
              lesson={
                lessonQuery.isFetching && !lesson ? null : lesson
              }
            />
          </Sheet>
        </div>
      )}
    </div>
  );
}

export function LearnPage() {
  return <LearnPageInner />;
}
