import { useState } from "react";
import type { DailyTotal } from "@/api";

export function DailyTrendChart({ data }: { data: DailyTotal[] }) {
  const [hovered, setHovered] = useState<DailyTotal | null>(null);

  if (!data || data.length === 0) return null;

  const maxTokens = Math.max(...data.map((d) => d.total_tokens), 1);
  const barMaxHeight = 120;
  const barWidth = Math.max(6, Math.min(28, 600 / data.length - 4));
  const chartHeight = barMaxHeight + 28;

  // Show month-day labels for every few bars
  const labelEvery = Math.max(1, Math.floor(data.length / 10));

  return (
    <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-ink">
            Daily token usage
          </div>
          <div className="text-[11px] text-mute">Last 30 days</div>
        </div>
        {hovered && (
          <div className="text-right text-[11px] text-body">
            <span className="font-medium text-ink">{hovered.date}</span>
            {" — "}
            <span className="font-semibold text-ink">
              {hovered.total_tokens.toLocaleString()}
            </span>{" "}
            tokens ({hovered.event_count} events)
          </div>
        )}
      </div>

      <div className="overflow-x-auto">
        <svg
          width={Math.max(300, data.length * (barWidth + 4) + 20)}
          height={chartHeight}
          className="block"
        >
          {data.map((d, i) => {
            const barH =
              d.total_tokens > 0
                ? Math.max(2, (d.total_tokens / maxTokens) * barMaxHeight)
                : 0;
            const x = i * (barWidth + 4) + 10;
            const y = barMaxHeight - barH;
            const isHovered = hovered?.date === d.date;

            return (
              <g key={d.date}>
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={barH}
                  rx={2}
                  className={
                    isHovered
                      ? "fill-ink"
                      : d.total_tokens > 0
                        ? "fill-ink/40 hover:fill-ink/60"
                        : "fill-hairline"
                  }
                  onMouseEnter={() => setHovered(d)}
                  onMouseLeave={() => setHovered(null)}
                  style={{ cursor: "pointer" }}
                />
                {i % labelEvery === 0 && (
                  <text
                    x={x + barWidth / 2}
                    y={chartHeight - 6}
                    textAnchor="middle"
                    className="fill-mute"
                    style={{ fontSize: 9 }}
                  >
                    {d.date.slice(5)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
