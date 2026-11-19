import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { EmptyState, ListSkeleton } from "../components/Skeleton";
import { recentProjectIds } from "../lib/recent";
import { GuestNote } from "./AccountDashboard";

interface HistoryEvent {
  project_id: string;
  project_name: string;
  kind: string;
  message: string;
  bug_id: string | null;
  at: string;
}

interface HistoryPayload {
  guest: boolean;
  projects: { id: string; name: string }[];
  events: HistoryEvent[];
}

const FILTERS: { key: string; label: string; match: (kind: string) => boolean }[] = [
  { key: "all", label: "All", match: () => true },
  { key: "scans", label: "Scans", match: (kind) => kind.startsWith("scan") || kind === "upload" },
  { key: "bugs", label: "Bugs", match: (kind) => kind.startsWith("bug") },
  { key: "fixes", label: "Fixes & decisions", match: (kind) => /patch|fix|approve|reject|edit|skip|rollback|decision|apply/.test(kind) },
  { key: "tests", label: "Tests", match: (kind) => kind.includes("test") },
];

function icon(kind: string): string {
  if (kind.includes("test")) return "🧪";
  if (kind.startsWith("bug")) return "🐞";
  if (/reject/.test(kind)) return "✋";
  if (/patch|fix|approve|apply/.test(kind)) return "✅";
  if (/rollback/.test(kind)) return "↩️";
  if (kind === "upload") return "📥";
  return "🔍";
}

function dayLabel(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

/** Account-level history: every scan, bug and decision across the user's projects. */
export default function AccountHistory() {
  const { user } = useAuth();
  const [data, setData] = useState<HistoryPayload | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    const ids = user ? "" : recentProjectIds().join(",");
    api<HistoryPayload>(`/api/me/history?ids=${encodeURIComponent(ids)}`)
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, [user]);

  const groups = useMemo(() => {
    const match = FILTERS.find((item) => item.key === filter)?.match ?? (() => true);
    const byDay = new Map<string, HistoryEvent[]>();
    for (const event of (data?.events || []).filter((item) => match(item.kind))) {
      const day = dayLabel(event.at);
      byDay.set(day, [...(byDay.get(day) || []), event]);
    }
    return [...byDay.entries()];
  }, [data, filter]);

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-semibold">History</h1>
      <p className="mt-2 text-mist">Every scan, bug, fix and decision across your projects, newest first.</p>
      {data?.guest && <GuestNote />}
      {error && <p className="mt-4 text-bug">{error}</p>}

      <div className="mt-5 flex flex-wrap gap-2" role="tablist" aria-label="Filter history">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={filter === item.key}
            onClick={() => setFilter(item.key)}
            className={`rounded-full border px-3 py-1.5 text-sm ${filter === item.key ? "border-ink bg-ink text-cream" : "border-line bg-panel hover:border-ink"}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {!data && !error && (
        <div className="mt-6">
          <ListSkeleton rows={6} />
        </div>
      )}
      {data && data.events.length === 0 && (
        <div className="mt-6">
          <EmptyState title="Nothing here yet">
            <p>Upload code or open an example; each scan, fix and test run will be recorded here.</p>
            <Link to="/upload" className="btn-primary mt-4 inline-block">Upload code</Link>
          </EmptyState>
        </div>
      )}
      {data && data.events.length > 0 && groups.length === 0 && (
        <p className="mt-6 text-sm text-mist">No events of this type yet.</p>
      )}

      {groups.map(([day, events]) => (
        <section key={day} className="mt-6">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-mist">{day}</h2>
          <ol className="mt-2 space-y-2">
            {events.map((event, index) => (
              <li key={`${event.at}-${index}`} className="flex gap-3 rounded-2xl border border-line bg-panel px-4 py-3">
                <span aria-hidden="true">{icon(event.kind)}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm">{event.message}</p>
                  <p className="mt-1 text-xs text-mist">
                    <Link to={`/p/${event.project_id}/history`} className="font-medium text-ink underline-offset-2 hover:underline">
                      {event.project_name}
                    </Link>{" "}
                    · {new Date(event.at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
                    {event.bug_id && (
                      <>
                        {" · "}
                        <Link to={`/p/${event.project_id}/explain/${event.bug_id}`} className="underline-offset-2 hover:underline">
                          open bug
                        </Link>
                      </>
                    )}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}
