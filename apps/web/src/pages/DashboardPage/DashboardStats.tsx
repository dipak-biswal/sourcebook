import { Bot, Files, MessageCircle, StickyNote } from "lucide-react";
import { Link } from "react-router-dom";
import { useDashboardPage } from "./dashboard-page-context";

const STATS = [
  {
    key: "documents",
    icon: Files,
    label: "Documents",
    to: "/documents",
    color: "text-blue-500",
    emptyAction: "Upload a document",
    pendingAction: "Finish ingest",
    hasAction: "Manage documents",
  },
  {
    key: "conversations",
    icon: MessageCircle,
    label: "Chat sessions",
    to: "/chat",
    color: "text-emerald-500",
    emptyAction: "Start chatting",
    hasAction: "Open chat",
  },
  {
    key: "agentRuns",
    icon: Bot,
    label: "Agent runs",
    to: "/agents",
    color: "text-violet-500",
    emptyAction: "Start agent run",
    hasAction: "View runs",
  },
  {
    key: "notes",
    icon: StickyNote,
    label: "Notes",
    to: "/notes",
    color: "text-amber-500",
    emptyAction: "Browse notes",
    hasAction: "View notes",
  },
] as const;

type StatKey = (typeof STATS)[number]["key"];

function actionLabel(
  stat: (typeof STATS)[number],
  count: number,
  readyDocumentsCount: number,
): string {
  if (count === 0) return stat.emptyAction;
  if (stat.key === "documents" && readyDocumentsCount === 0 && stat.pendingAction) {
    return stat.pendingAction;
  }
  return stat.hasAction;
}

export function DashboardStats() {
  const {
    documentsCount,
    readyDocumentsCount,
    conversationsCount,
    agentRunsCount,
    notesCount,
    loading,
  } = useDashboardPage();

  const counts: Record<StatKey, number> = {
    documents: documentsCount,
    conversations: conversationsCount,
    agentRuns: agentRunsCount,
    notes: notesCount,
  };

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {STATS.map((stat) => {
        const { key, icon: Icon, label, to, color } = stat;
        const count = counts[key];
        const action = actionLabel(stat, count, readyDocumentsCount);

        return (
          <Link
            key={key}
            to={to}
            className="group flex items-center gap-3 rounded-vercel-md border border-hairline bg-canvas p-3.5 transition-colors hover:border-ink/20 hover:bg-canvas-soft-2"
            aria-label={
              loading
                ? label
                : `${label}: ${count}. ${action}`
            }
          >
            <div className={`${color} transition-opacity group-hover:opacity-90`}>
              <Icon className="h-5 w-5" strokeWidth={1.5} />
            </div>
            <div className="min-w-0">
              <div className="text-lg font-semibold tracking-tight text-ink">
                {loading ? "—" : count}
              </div>
              <div className="truncate text-[11px] text-mute">{label}</div>
              {!loading && (
                <div className="mt-0.5 truncate text-[11px] font-medium text-ink group-hover:underline group-hover:underline-offset-2">
                  {action} →
                </div>
              )}
            </div>
          </Link>
        );
      })}
    </div>
  );
}