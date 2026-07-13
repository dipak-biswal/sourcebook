import { Bot, Files, MessageCircle, StickyNote } from "lucide-react";
import { useDashboardPage } from "./dashboard-page-context";

const STATS = [
  { key: "documents", icon: Files, label: "Documents", color: "text-blue-500" },
  { key: "conversations", icon: MessageCircle, label: "Chat sessions", color: "text-emerald-500" },
  { key: "agentRuns", icon: Bot, label: "Agent runs", color: "text-violet-500" },
  { key: "notes", icon: StickyNote, label: "Notes", color: "text-amber-500" },
] as const;

export function DashboardStats() {
  const { documentsCount, conversationsCount, agentRunsCount, notesCount, loading } = useDashboardPage();

  const counts: Record<string, number> = {
    documents: documentsCount,
    conversations: conversationsCount,
    agentRuns: agentRunsCount,
    notes: notesCount,
  };

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {STATS.map(({ key, icon: Icon, label, color }) => (
        <div
          key={key}
          className="flex items-center gap-3 rounded-vercel-md border border-hairline bg-canvas p-3.5"
        >
          <div className={`${color}`}>
            <Icon className="h-5 w-5" strokeWidth={1.5} />
          </div>
          <div className="min-w-0">
            <div className="text-lg font-semibold tracking-tight text-ink">
              {loading ? "—" : counts[key]}
            </div>
            <div className="truncate text-[11px] text-mute">{label}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
