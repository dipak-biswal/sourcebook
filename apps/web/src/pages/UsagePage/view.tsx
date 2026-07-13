import { Activity, Loader2, RefreshCw } from "lucide-react";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardSkeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/utils";

import type { UsagePageViewProps } from "@/types/page-props";

export function UsagePageView({
  data,
  error,
  loading,
  onRefresh,
  onLogout,
}: UsagePageViewProps) {
  const kindEntries = Object.entries(data?.by_kind ?? {});

  return (
    <div className="app-shell">
      <AppHeader onLogout={onLogout} />

      <main id="main-content" tabIndex={-1} className="document-scroll min-h-0 flex-1 overflow-y-auto px-4 py-6 outline-none sm:px-6 sm:py-8">
        <div className="mx-auto max-w-3xl">
          <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-ink" strokeWidth={1.5} />
                <h1 className="text-display-sm font-semibold tracking-tight text-ink">
                  Usage
                </h1>
              </div>
              <p className="mt-1 text-body-sm text-mute">
                Token usage logged for your account (chat, stream, agent runs).
                OpenAI dashboard is the source of truth for billing.
              </p>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={loading}
              onClick={onRefresh}
            >
              {loading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />
              )}
              Refresh
            </Button>
          </div>

          {error && (
            <Alert variant="danger" className="mb-4">
              {error}
            </Alert>
          )}

          {loading && !data ? (
            <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <CardSkeleton />
              <CardSkeleton />
            </div>
          ) : (
            <>
              <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
                  <div className="text-xs font-medium uppercase tracking-wide text-mute">
                    Events
                  </div>
                  <div className="mt-1 text-2xl font-semibold text-ink">
                    {data?.event_count ?? 0}
                  </div>
                </div>
                <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
                  <div className="text-xs font-medium uppercase tracking-wide text-mute">
                    Total tokens (logged)
                  </div>
                  <div className="mt-1 text-2xl font-semibold text-ink">
                    {(data?.total_tokens ?? 0).toLocaleString()}
                  </div>
                </div>
              </div>

              {kindEntries.length > 0 && (
                <div className="mb-6 rounded-vercel-md border border-hairline bg-canvas p-4">
                  <div className="mb-3 text-sm font-semibold text-ink">
                    By kind
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {kindEntries.map(([kind, tokens]) => (
                      <Badge key={kind} variant="outline" className="gap-1.5">
                        <span className="font-medium text-ink">{kind}</span>
                        <span className="text-mute">
                          {tokens.toLocaleString()} tokens
                        </span>
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              <div className="rounded-vercel-md border border-hairline bg-canvas">
                <div className="border-b border-hairline px-4 py-3 text-sm font-semibold text-ink">
                  Recent activity
                </div>
                {!data?.recent?.length ? (
                  <p className="px-4 py-10 text-center text-sm text-mute">
                    No usage yet. Send a chat message or run an agent, then
                    refresh.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[560px] text-left text-sm">
                      <thead>
                        <tr className="border-b border-hairline text-xs text-mute">
                          <th className="px-4 py-2 font-medium">When</th>
                          <th className="px-4 py-2 font-medium">Kind</th>
                          <th className="px-4 py-2 font-medium">Model</th>
                          <th className="px-4 py-2 font-medium">Tokens</th>
                          <th className="px-4 py-2 font-medium">Notes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.recent.map((row) => {
                          const estimated =
                            row.meta &&
                            typeof row.meta === "object" &&
                            "estimated" in row.meta &&
                            row.meta.estimated === true;
                          const denied =
                            row.meta &&
                            typeof row.meta === "object" &&
                            "denied" in row.meta &&
                            row.meta.denied === true;
                          return (
                            <tr
                              key={row.id}
                              className="border-b border-hairline last:border-0"
                            >
                              <td className="px-4 py-2.5 text-body whitespace-nowrap">
                                {formatDateTime(row.created_at)}
                              </td>
                              <td className="px-4 py-2.5 text-ink">
                                {row.kind}
                              </td>
                              <td className="max-w-[160px] truncate px-4 py-2.5 text-body">
                                {row.model ?? "—"}
                              </td>
                              <td className="px-4 py-2.5 font-medium text-ink">
                                {row.total_tokens != null
                                  ? row.total_tokens.toLocaleString()
                                  : "—"}
                                {row.prompt_tokens != null &&
                                  row.completion_tokens != null && (
                                    <span className="ml-1 text-xs font-normal text-mute">
                                      ({row.prompt_tokens}+
                                      {row.completion_tokens})
                                    </span>
                                  )}
                              </td>
                              <td className="px-4 py-2.5">
                                <div className="flex flex-wrap gap-1">
                                  {estimated && (
                                    <Badge variant="secondary">estimated</Badge>
                                  )}
                                  {denied && (
                                    <Badge variant="warning">denied</Badge>
                                  )}
                                  {!estimated && !denied && (
                                    <span className="text-mute">—</span>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
