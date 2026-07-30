import { Bot, FileUp, GraduationCap, MessageCircle } from "lucide-react";
import { Link } from "react-router-dom";

const ACTIONS = [
  { to: "/learn", icon: GraduationCap, label: "Learn", desc: "Study your curriculum" },
  { to: "/chat", icon: MessageCircle, label: "Ask", desc: "Grounded Q&A on sources" },
  { to: "/documents", icon: FileUp, label: "Library", desc: "Upload and manage docs" },
  { to: "/agents", icon: Bot, label: "Agents", desc: "Deep research runs" },
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
