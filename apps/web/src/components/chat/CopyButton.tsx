import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

export function CopyButton({
  text,
  className,
  label = "Copy",
}: {
  text: string;
  className?: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function onCopy() {
    const value = text.trim();
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* ignore */
    }
  }

  return (
    <button
      type="button"
      onClick={() => void onCopy()}
      className={cn(
        "inline-flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 text-[11px] font-medium text-mute transition-colors hover:bg-canvas-soft-2 hover:text-ink",
        className,
      )}
      title={label}
    >
      {copied ? (
        <Check className="h-3 w-3" strokeWidth={1.5} />
      ) : (
        <Copy className="h-3 w-3" strokeWidth={1.5} />
      )}
      {copied ? "Copied" : label}
    </button>
  );
}
