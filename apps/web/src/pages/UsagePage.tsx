import { useCallback, useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Activity, Loader2, RefreshCw } from "lucide-react";
import { api, getToken, type UsageSummary } from "@/api";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatError } from "@/lib/utils";

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function UsagePage() {
  const navigate = useNavigate();
  const [data, setData] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const summary = await api.usageSummary();
      setData(summary);
    } catch (err) {
      setError(formatError(err));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    void load();
  }, [load]);

  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  const kindEntries = Object.entries(data?.by_kind ?? {});

  return (
    <div className="flex h-full flex-col overflow-hidden bg-canvas-soft">
      <AppHeader
        onLogout={() => {
          navigate("/login", { replace: true });
        }}
      />

      <main className="document-scroll min-h-0 flex-1 overflow-y-auto px-6 py-8">
        <div className="mx-auto max-w-3xl">
          <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-ink" strokeWidth={1.5} />
                <h1 className="text-display-sm font-semibold text-ink">Usage</h1>
              </div>
              <p className="mt-1 text-body-sm text-mute">
                Token usage logged by Sourcebook for your account (chat / stream).
                OpenAI dashboard is the source of truth for billing.
              </p>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={loading}
              onClick={() => void load()}
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
            <p className="flex items-center gap-2 text-sm text-mute">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading usage…
            </p>
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
                  <p className="px-4 py-8 text-center text-sm text-mute">
                    No usage yet. Send a chat message, then refresh.
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
                            row.meta.estimated === true;
                          const denied =
                            row.meta &&
                            typeof row.meta === "object" &&
                            row.meta.denied === true;
                          return (
                            <tr
                              key={row.id}
                              className="border-b border-hairline last:border-0"
                            >
                              <td className="px-4 py-2.5 text-body whitespace-nowrap">
                                {formatWhen(row.created_at)}
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
