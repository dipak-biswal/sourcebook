import { useCallback, useEffect, useMemo, useState } from "react";
import { Archive, BookOpen, Loader2, RefreshCw, RotateCcw } from "lucide-react";
import { api, type CurriculumTopic } from "@/api";
import { Button } from "@/components/ui/button";

/** Curriculum topics under Settings → Workspaces (list, archive, restore). */
export function WorkspaceCurriculumPanel({
  workspaceId,
  workspaceName,
}: {
  workspaceId: string;
  workspaceName: string;
}) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [domain, setDomain] = useState("");
  const [topics, setTopics] = useState<CurriculumTopic[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (refresh = false) => {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      setError(null);
      try {
        const data = refresh
          ? await api.refreshCurriculum(workspaceId)
          : await api.getCurriculum(workspaceId, { includeArchived: true });
        // After force-refresh, re-fetch with archived so restore list stays.
        if (refresh) {
          const withArchived = await api.getCurriculum(workspaceId, {
            includeArchived: true,
          });
          setEnabled(withArchived.enabled);
          setDomain(withArchived.domain || "");
          setTopics(withArchived.topics || []);
        } else {
          setEnabled(data.enabled);
          setDomain(data.domain || "");
          setTopics(data.topics || []);
        }
      } catch (e) {
        setEnabled(false);
        setTopics([]);
        setError(e instanceof Error ? e.message : null);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [workspaceId],
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  const active = useMemo(
    () => topics.filter((t) => (t.status || "active") !== "archived"),
    [topics],
  );
  const archived = useMemo(
    () => topics.filter((t) => t.status === "archived"),
    [topics],
  );

  async function setStatus(topic: CurriculumTopic, status: "active" | "archived") {
    setBusyId(topic.id);
    setError(null);
    try {
      const updated = await api.patchCurriculumTopic(workspaceId, topic.id, {
        status,
      });
      setTopics((prev) =>
        prev.map((t) => (t.id === topic.id ? { ...t, ...updated } : t)),
      );
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : status === "archived"
            ? "Could not archive topic"
            : "Could not restore topic",
      );
    } finally {
      setBusyId(null);
    }
  }

  if (loading) {
    return (
      <div className="mt-2 flex items-center gap-1.5 text-[10px] text-mute">
        <Loader2 className="h-3 w-3 animate-spin" />
        Checking topics…
      </div>
    );
  }

  if (!enabled) return null;

  return (
    <div className="mt-2 rounded-[6px] border border-hairline bg-canvas-soft px-2.5 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <BookOpen className="h-3 w-3 shrink-0 text-mute" strokeWidth={1.5} />
          <span className="truncate text-[11px] font-medium text-ink">
            Topics{domain ? ` · ${domain}` : ""}
          </span>
        </div>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-6 gap-1 px-1.5 text-[10px]"
          disabled={refreshing}
          onClick={() => void load(true)}
        >
          {refreshing ? (
            <Loader2 className="h-2.5 w-2.5 animate-spin" />
          ) : (
            <RefreshCw className="h-2.5 w-2.5" strokeWidth={1.5} />
          )}
          Refresh
        </Button>
      </div>
      {error && <p className="mt-1 text-[10px] text-mute">{error}</p>}

      {active.length === 0 ? (
        <p className="mt-1 text-[10px] text-mute">
          No active topics. Open Agents for {workspaceName} to generate the catalog
          {archived.length ? ", or restore one below" : ""}.
        </p>
      ) : (
        <ul className="mt-1.5 max-h-32 space-y-0.5 overflow-y-auto">
          {active.map((t) => (
            <li
              key={t.id}
              className="flex items-center gap-1 text-[10px] text-body"
              title={t.summary || t.title}
            >
              <span className="min-w-0 flex-1 truncate">
                <span className="font-medium text-ink">{t.title}</span>
                {Object.keys(t.preferences || {}).length > 0 ? (
                  <span className="text-mute"> · prefs</span>
                ) : null}
                {t.source === "custom" ? (
                  <span className="text-mute"> · custom</span>
                ) : null}
              </span>
              <button
                type="button"
                className="shrink-0 rounded p-0.5 text-mute hover:bg-canvas hover:text-ink"
                title="Archive topic (hide from Agents)"
                disabled={busyId === t.id}
                onClick={() => void setStatus(t, "archived")}
              >
                {busyId === t.id ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Archive className="h-3 w-3" strokeWidth={1.5} />
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {archived.length > 0 && (
        <div className="mt-2 border-t border-hairline/70 pt-1.5">
          <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-mute">
            Archived
          </p>
          <ul className="max-h-24 space-y-0.5 overflow-y-auto">
            {archived.map((t) => (
              <li
                key={t.id}
                className="flex items-center gap-1 text-[10px] text-mute"
                title={t.summary || t.title}
              >
                <span className="min-w-0 flex-1 truncate line-through">
                  {t.title}
                </span>
                <button
                  type="button"
                  className="inline-flex shrink-0 items-center gap-0.5 rounded p-0.5 text-mute hover:bg-canvas hover:text-ink"
                  title="Restore to Agents catalog"
                  disabled={busyId === t.id}
                  onClick={() => void setStatus(t, "active")}
                >
                  {busyId === t.id ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <>
                      <RotateCcw className="h-3 w-3" strokeWidth={1.5} />
                      <span className="text-[9px]">Restore</span>
                    </>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
