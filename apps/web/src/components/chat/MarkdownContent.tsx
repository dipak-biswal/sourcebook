import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

function CodeBlock({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  const match = /language-(\w+)/.exec(className ?? "");
  const code = String(children ?? "").replace(/\n$/, "");
  const lang = match ? match[1] : "";

  if (match) {
    return (
      <div className="not-prose my-2 overflow-hidden rounded-[8px] border border-hairline">
        {lang && (
          <div className="border-b border-hairline bg-canvas-soft px-3 py-1 text-[10px] font-medium uppercase tracking-wide text-mute">
            {lang}
          </div>
        )}
        <pre className="m-0 overflow-x-auto bg-canvas-soft-2 p-3 font-mono text-[0.8125rem] leading-relaxed text-body">
          <code>{code}</code>
        </pre>
      </div>
    );
  }

  return (
    <code className="rounded-[4px] bg-canvas-soft-2 px-1.5 py-0.5 font-mono text-[0.8125rem] text-ink">
      {children}
    </code>
  );
}

const components = {
  code: CodeBlock,
  pre: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="my-1.5 leading-relaxed text-body first:mt-0 last:mb-0">{children}</p>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="my-1.5 list-disc space-y-0.5 pl-5 text-body">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="my-1.5 list-decimal space-y-0.5 pl-5 text-body">{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="leading-relaxed">{children}</li>
  ),
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="my-3 border-b border-hairline pb-1 text-base font-bold text-ink first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="my-2.5 border-b border-hairline/60 pb-0.5 text-sm font-bold text-ink">
      {children}
    </h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="my-2 text-sm font-semibold text-ink">{children}</h3>
  ),
  h4: ({ children }: { children?: React.ReactNode }) => (
    <h4 className="my-1.5 text-xs font-semibold text-ink/80">{children}</h4>
  ),
  blockquote: ({ children }: { children?: React.ReactNode }) => (
    <blockquote className="my-2 border-l-[3px] border-warning-border py-0.5 pl-3 text-body italic">
      {children}
    </blockquote>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold text-ink">{children}</strong>
  ),
  a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-underline hover:opacity-80"
    >
      {children}
    </a>
  ),
  hr: () => <hr className="my-3 border-hairline" />,
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="my-2 overflow-x-auto rounded-[6px] border border-hairline">
      <table className="w-full text-left text-xs text-body">{children}</table>
    </div>
  ),
  th: ({ children }: { children?: React.ReactNode }) => (
    <th className="border-b border-hairline bg-canvas-soft px-3 py-2 font-semibold text-ink">
      {children}
    </th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td className="border-b border-hairline/50 px-3 py-2">{children}</td>
  ),
};

export function MarkdownContent({ content, className }: { content: string; className?: string }) {
  return (
    <div className={cn("prose-custom text-sm", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
