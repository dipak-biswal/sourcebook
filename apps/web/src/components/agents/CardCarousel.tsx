import { useCallback, useEffect, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/** Cycled per card index purely for visual variety behind the icon tile. */
const CARD_GRADIENTS = [
  "from-[#ffd9b3] to-[#ff9d5c]", // peach
  "from-[#bcd7ff] to-[#5b8def]", // blue
  "from-[#e3c9ff] to-[#a45bef]", // violet
  "from-[#c8f0d8] to-[#4fbf7f]", // green
];

function ScrollProgressBar({
  scrollRef,
}: {
  scrollRef: React.RefObject<HTMLDivElement | null>;
}) {
  const [metrics, setMetrics] = useState({ widthPct: 100, leftPct: 0 });

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const { scrollLeft, scrollWidth, clientWidth } = el;
      if (scrollWidth <= clientWidth + 1) {
        setMetrics({ widthPct: 100, leftPct: 0 });
        return;
      }
      setMetrics({
        widthPct: Math.max(15, (clientWidth / scrollWidth) * 100),
        leftPct: (scrollLeft / scrollWidth) * 100,
      });
    };
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(update);
    };
    update();
    el.addEventListener("scroll", onScroll, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", onScroll);
      ro.disconnect();
      if (raf) cancelAnimationFrame(raf);
    };
  }, [scrollRef]);

  if (metrics.widthPct >= 100) return null;

  return (
    <div className="relative mt-2 h-1 w-full overflow-hidden rounded-full bg-canvas-soft-2">
      <div
        className="absolute inset-y-0 rounded-full bg-mute/60"
        style={{ width: `${metrics.widthPct}%`, left: `${metrics.leftPct}%` }}
      />
    </div>
  );
}

/** Horizontal scroll-snap shell with a drag-handle-style progress bar underneath. */
export function CardCarousel({
  ariaLabel,
  children,
}: {
  ariaLabel: string;
  children: React.ReactNode;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const el = scrollRef.current;
      if (!el) return;
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        el.scrollBy({
          left: e.key === "ArrowRight" ? el.clientWidth * 0.8 : -el.clientWidth * 0.8,
          behavior: "smooth",
        });
      }
    },
    [],
  );

  return (
    <div>
      <div
        ref={scrollRef}
        role="list"
        aria-label={ariaLabel}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        className="document-scroll flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-smooth pb-1 focus-visible:outline-none"
      >
        {children}
      </div>
      <ScrollProgressBar scrollRef={scrollRef} />
    </div>
  );
}

export function TopicCard({
  index,
  icon: Icon,
  eyebrow,
  title,
  description,
  expanded,
  ctaLabel,
  onCta,
}: {
  index: number;
  icon: LucideIcon;
  eyebrow?: string;
  title: string;
  description?: string;
  expanded?: boolean;
  ctaLabel: string;
  onCta?: () => void;
}) {
  const dark = index % 2 === 0;
  const gradient = CARD_GRADIENTS[index % CARD_GRADIENTS.length];

  return (
    <div
      role="listitem"
      className={cn(
        "flex w-[78%] shrink-0 snap-start flex-col overflow-hidden rounded-vercel-xl border sm:w-[55%] md:w-[280px]",
        dark
          ? "border-transparent bg-[var(--carousel-dark-bg)] text-[var(--carousel-dark-fg)]"
          : "border-[var(--carousel-light-border)] bg-[var(--carousel-light-bg)] text-[var(--carousel-light-fg)]",
      )}
    >
      <div
        className={cn(
          "flex aspect-[4/3] items-center justify-center bg-gradient-to-br",
          gradient,
        )}
      >
        <Icon className="h-10 w-10 text-black/65" strokeWidth={1.25} />
      </div>
      <div className="flex flex-1 flex-col gap-1.5 p-4">
        {eyebrow && (
          <span
            className={cn(
              "text-[10px] font-bold uppercase tracking-wide",
              dark
                ? "text-[var(--carousel-dark-mute)]"
                : "text-[var(--carousel-light-mute)]",
            )}
          >
            {eyebrow}
          </span>
        )}
        <h4
          className={cn(
            "font-semibold leading-snug",
            description
              ? "text-base line-clamp-2"
              : cn("text-sm leading-relaxed", !expanded && "line-clamp-4"),
          )}
        >
          {title}
        </h4>
        {description && (
          <p
            className={cn(
              "text-xs leading-relaxed",
              !expanded && "line-clamp-3",
              dark
                ? "text-[var(--carousel-dark-mute)]"
                : "text-[var(--carousel-light-mute)]",
            )}
          >
            {description}
          </p>
        )}
        {onCta && (
          <button
            type="button"
            onClick={onCta}
            className={cn(
              "mt-auto inline-flex w-fit items-center rounded-full px-3 py-1.5 pt-3 text-[11px] font-medium transition-opacity hover:opacity-85",
              dark
                ? "bg-[var(--carousel-light-bg)] text-[var(--carousel-dark-bg)]"
                : "bg-[var(--carousel-dark-bg)] text-[var(--carousel-light-bg)]",
            )}
          >
            {ctaLabel}
          </button>
        )}
      </div>
    </div>
  );
}

/** Manages expand/collapse state for a set of cards; used by key_points and key_terms. */
export function TopicCardCarousel({
  ariaLabel,
  cards,
  icon,
  affordance,
  onCardExpand,
}: {
  ariaLabel: string;
  cards: { title: string; description?: string; eyebrow?: string }[];
  icon: LucideIcon;
  affordance: string;
  onCardExpand?: (affordance: string, label: string) => void;
}) {
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(new Set());

  return (
    <CardCarousel ariaLabel={ariaLabel}>
      {cards.map((card, i) => {
        const isExpanded = expanded.has(i);
        return (
          <TopicCard
            key={i}
            index={i}
            icon={icon}
            eyebrow={card.eyebrow}
            title={card.title}
            description={card.description}
            expanded={isExpanded}
            ctaLabel={isExpanded ? "Show less" : "Learn more"}
            onCta={() => {
              setExpanded((prev) => {
                const next = new Set(prev);
                if (next.has(i)) next.delete(i);
                else next.add(i);
                return next;
              });
              onCardExpand?.(affordance, (card.title || card.description || "").slice(0, 60));
            }}
          />
        );
      })}
    </CardCarousel>
  );
}
