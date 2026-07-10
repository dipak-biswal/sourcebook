type SourcebookIconProps = {
  size?: "sm" | "md" | "lg";
  className?: string;
};

const sizes = {
  sm: "h-5 w-5",
  md: "h-8 w-8",
  lg: "h-10 w-10",
} as const;

/** Minimal mark — open book + mark, matches agent-docs ink/currentColor style */
export function SourcebookIcon({
  size = "md",
  className = "",
}: SourcebookIconProps) {
  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden="true"
      className={`shrink-0 text-ink ${sizes[size]} ${className}`}
    >
      <path
        d="M8 12.5c0-1.4 1.1-2.5 2.5-2.5H22v28H10.5A2.5 2.5 0 0 1 8 35.5v-23Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path
        d="M40 12.5c0-1.4-1.1-2.5-2.5-2.5H26v28h11.5a2.5 2.5 0 0 0 2.5-2.5v-23Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path
        d="M24 10v28"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx="24" cy="8" r="2" fill="currentColor" />
    </svg>
  );
}
