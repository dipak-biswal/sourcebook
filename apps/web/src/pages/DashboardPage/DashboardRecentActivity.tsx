import { Bot, Files, MessageCircle, StickyNote } from "lucide-react";
import { Link } from "react-router-dom";
import { useDashboardPage } from "./DashboardPageContext";

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

const TYPE_ICONS = {
  document: Files,
  conversation: MessageCircle,
  agent_run: Bot,
  note: StickyNote,
} as const;

const TYPE_COLORS = {
  document: "text-blue-500",
  conversation: "text-emerald-500",
  agent_run: "text-violet-500",
  note: "text-amber-500",
} as const;

export function DashboardRecentActivity() {
  const { recent, loading } = useDashboardPage();

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-14 animate-pulse rounded-vercel-md border border-hairline bg-canvas-soft"
          />
        ))}
      </div>
    );
  }

  if (recent.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-mute">
        No activity yet. Upload a document or start a chat to get started.
      </p>
    );
  }

  return (
    <div className="space-y-1">
      {recent.map((item) => {
        const Icon = TYPE_ICONS[item.type];
        const colorClass = TYPE_COLORS[item.type];
        return (
          <Link
            key={`${item.type}-${item.id}`}
            to={item.href}
            className="flex items-center gap-3 rounded-[6px] border border-transparent px-3 py-2.5 transition-colors hover:border-hairline hover:bg-canvas-soft-2"
          >
            <div className={colorClass}>
              <Icon className="h-4 w-4" strokeWidth={1.5} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-ink">
                {item.label}
              </div>
              <div className="flex items-center gap-2 text-[11px] text-mute">
                <span>{item.subtitle}</span>
                <span>·</span>
                <span>{formatDate(item.created_at)}</span>
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
