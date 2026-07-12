import { Bot, FileUp, MessageCircle, StickyNote } from "lucide-react";
import { Link } from "react-router-dom";

const ACTIONS = [
  { to: "/chat", icon: MessageCircle, label: "New chat", desc: "Ask grounded questions" },
  { to: "/documents", icon: FileUp, label: "Upload document", desc: "Add sources to ingest" },
  { to: "/agents", icon: Bot, label: "Agent run", desc: "Tools with HITL" },
  { to: "/notes", icon: StickyNote, label: "View notes", desc: "Browse saved notes" },
] as const;

export function DashboardQuickActions() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {ACTIONS.map(({ to, icon: Icon, label, desc }) => (
        <Link
          key={to}
          to={to}
          className="group flex items-center gap-3 rounded-vercel-md border border-hairline bg-canvas p-3.5 transition-colors hover:bg-canvas-soft-2"
        >
          <div className="text-mute transition-colors group-hover:text-ink">
            <Icon className="h-5 w-5" strokeWidth={1.5} />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium text-ink">{label}</div>
            <div className="truncate text-[11px] text-mute">{desc}</div>
          </div>
        </Link>
      ))}
    </div>
  );
}
