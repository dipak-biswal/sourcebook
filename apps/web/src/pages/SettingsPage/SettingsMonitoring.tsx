import { useCallback, useEffect, useState } from "react";
import { Activity, Loader2, RefreshCw, Users } from "lucide-react";
import { api, type MonitoringOverview } from "@/api";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-errors";
import { formatDate, formatError } from "@/lib/utils";

function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: number | string;
  hint?: string;
}) {
  return (
    <div className="rounded-[8px] border border-hairline bg-canvas-soft px-3 py-2.5">
      <div className="text-[11px] font-medium uppercase tracking-wide text-mute">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-ink">
        {value}
      </div>
      {hint ? <p className="mt-0.5 text-[11px] text-mute">{hint}</p> : null}
    </div>
  );
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return "—";
    const sec = Math.round((Date.now() - t) / 1000);
    if (sec < 45) return "just now";
    if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
    if (sec < 86400 * 14) return `${Math.floor(sec / 86400)}d ago`;
    return formatDate(iso);
  } catch {
    return "—";
  }
}

export function SettingsMonitoring() {
  const [data, setData] = useState<MonitoringOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setForbidden(false);
    try {
      const overview = await api.monitoringUsers();
      setData(overview);
    } catch (err) {
      const msg = formatError(err);
      if (err instanceof ApiError && err.status === 403) {
        setForbidden(true);
        setError("Monitoring is restricted to admin users.");
      } else {
        setError(msg);
      }
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 60_000);
    return () => window.clearInterval(id);
  }, [load]);

  if (loading && !data) {
    return (
      <div className="flex items-center gap-2 rounded-vercel-md border border-hairline bg-canvas px-4 py-8 text-sm text-mute">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading activity…
      </div>
    );
  }

  if (forbidden) {
    return (
      <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
        <h2 className="text-sm font-semibold text-ink">Monitoring</h2>
        <p className="mt-2 text-xs text-body">
          This tab is limited to admin accounts. Ask an operator to add your
          email to <code className="rounded bg-canvas-soft px-1">ADMIN_EMAILS</code>{" "}
          on the API, or leave that variable empty to allow all signed-in users
          (self-hosted).
        </p>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="rounded-vercel-md border border-danger-border bg-danger-soft p-4">
        <p className="text-sm text-danger-text">{error}</p>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="mt-3"
          onClick={() => void load()}
        >
          Retry
        </Button>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
              <Activity className="h-4 w-4" strokeWidth={1.5} />
              User activity
            </h2>
            <p className="mt-1 text-xs text-mute">
              Online = last API activity within the last{" "}
              {data.online_window_minutes} minutes. Refreshes every minute.
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={loading}
            onClick={() => void load()}
            className="gap-1"
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
            Refresh
          </Button>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <StatCard label="Total users" value={data.total_users} />
          <StatCard
            label="Online now"
            value={data.online_now}
            hint={`Last ${data.online_window_minutes}m`}
          />
          <StatCard label="Active 24h" value={data.active_today} />
          <StatCard label="Active 7d" value={data.active_7d} />
        </div>
      </div>

      <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
          <Users className="h-4 w-4" strokeWidth={1.5} />
          Users
        </h3>
        {data.users.length === 0 ? (
          <p className="mt-3 text-xs text-mute">No registered users yet.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[28rem] text-left text-xs">
              <thead>
                <tr className="border-b border-hairline text-[11px] uppercase tracking-wide text-mute">
                  <th className="pb-2 pr-3 font-medium">Status</th>
                  <th className="pb-2 pr-3 font-medium">Email</th>
                  <th className="pb-2 pr-3 font-medium">Last seen</th>
                  <th className="pb-2 pr-3 font-medium">Last login</th>
                  <th className="pb-2 font-medium">Joined</th>
                </tr>
              </thead>
              <tbody>
                {data.users.map((u) => (
                  <tr
                    key={u.id}
                    className="border-b border-hairline/70 last:border-0"
                  >
                    <td className="py-2 pr-3">
                      <span
                        className={
                          u.online
                            ? "inline-flex items-center gap-1 rounded-full bg-success-soft px-2 py-0.5 text-[11px] font-medium text-success-text"
                            : "inline-flex items-center gap-1 rounded-full bg-canvas-soft px-2 py-0.5 text-[11px] font-medium text-mute"
                        }
                      >
                        <span
                          className={
                            u.online
                              ? "h-1.5 w-1.5 rounded-full bg-success-text"
                              : "h-1.5 w-1.5 rounded-full bg-mute"
                          }
                        />
                        {u.online ? "Online" : "Offline"}
                      </span>
                    </td>
                    <td className="py-2 pr-3 font-medium text-ink">{u.email}</td>
                    <td
                      className="py-2 pr-3 text-body"
                      title={u.last_seen_at ?? undefined}
                    >
                      {relativeTime(u.last_seen_at)}
                    </td>
                    <td
                      className="py-2 pr-3 text-body"
                      title={u.last_login_at ?? undefined}
                    >
                      {relativeTime(u.last_login_at)}
                    </td>
                    <td
                      className="py-2 text-body"
                      title={u.created_at ?? undefined}
                    >
                      {u.created_at ? formatDate(u.created_at) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
