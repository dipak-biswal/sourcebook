import { useState } from "react";
import { Link } from "react-router-dom";
import { Bot, MessageCircle, X } from "lucide-react";

const KEY = "sourcebook_chat_mode_tip_dismissed";

function isTipVisible(): boolean {
  try {
    return localStorage.getItem(KEY) !== "1";
  } catch {
    return true;
  }
}

export function ModeTip() {
  const [visible, setVisible] = useState(isTipVisible);

  if (!visible) return null;

  function dismiss() {
    try {
      localStorage.setItem(KEY, "1");
    } catch {
      /* ignore */
    }
    setVisible(false);
  }

  return (
    <div className="border-b border-warning-border bg-warning-soft px-4 py-2.5 sm:px-6">
      <div className="mx-auto flex max-w-2xl items-start gap-2">
        <div className="min-w-0 flex-1 text-xs leading-relaxed text-warning-text">
          <span className="font-semibold text-ink">Quick tip: </span>
          <span className="inline-flex items-center gap-1 font-medium text-ink">
            <MessageCircle className="inline h-3 w-3" strokeWidth={1.5} />
            Chat
          </span>{" "}
          answers from your documents with citations.{" "}
          <span className="inline-flex items-center gap-1 font-medium text-ink">
            <Bot className="inline h-3 w-3" strokeWidth={1.5} />
            Agent
          </span>{" "}
          runs tools in this thread (quick). For full run history, trace tabs,
          and notes, use the{" "}
          <Link
            to="/agents"
            className="font-medium text-ink underline-offset-2 hover:underline"
          >
            Agents page
          </Link>
          .
        </div>
        <button
          type="button"
          onClick={dismiss}
          className="shrink-0 rounded p-1 text-mute hover:bg-canvas/60 hover:text-ink"
          aria-label="Dismiss tip"
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}