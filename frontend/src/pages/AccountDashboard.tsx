import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { useAuth } from "../auth";
import CountUp from "../components/CountUp";
import { EmptyState, PageSkeleton } from "../components/Skeleton";
import { recentProjectIds } from "../lib/recent";

interface ProjectRow {
  id: string;
  name: string;
  source_type: string;
  created_at: string;
  scans: number;
  bugs: number;
  health: number | null;
  last_scan_at: string | null;
}

interface Overview {
  guest: boolean;
  totals: {
    projects: number;
    scans: number;
    bugs_found: number;
    fixes_approved: number;
    fixes_rejected: number;
    avg_health: number | null;
  };
  trend: { at: string; project: string; before: number; after: number }[];
  projects: ProjectRow[];
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function healthTone(score: number | null): string {
  if (score === null) return "text-mist";
  if (score >= 80) return "text-fixed";
  if (score >= 50) return "text-review";
  return "text-bug";
}

/** Account-level dashboard: every project the user (or this guest session) has worked on. */
export default function AccountDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const ids = user ? "" : recentProjectIds().join(",");
    api<Overview>(`/api/me/overview?ids=${encodeURIComponent(ids)}`)
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, [user]);

  if (error) return <p className="text-bug">{error}</p>;
  if (!data) return <PageSkeleton label="Loading your dashboard" />;

  const { totals } = data;
  const stats = [
    ["Projects", totals.projects],
    ["Scans run", totals.scans],
    ["Open bugs", totals.bugs_found],
    ["Fixes approved", totals.fixes_approved],
    ["Fixes rejected", totals.fixes_rejected],
  ] as const;

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="text-3xl font-semibold">Your dashboard</h1>
      <p className="mt-2 text-mist">Everything across your projects: scans, bugs, decisions and how healthy the code is now.</p>
      {data.guest && <GuestNote />}

      {totals.projects === 0 ? (
        <div className="mt-8">
          <EmptyState title="No projects yet">
            <p>Upload code or open an example, and your progress shows up here.</p>
            <div className="mt-4 flex flex-wrap justify-center gap-3">
              <Link to="/upload" className="btn-primary">Upload code</Link>
              <Link to="/#examples" className="btn-secondary">Try an example</Link>
            </div>
          </EmptyState>
        </div>
      ) : (
        <>
          <section className="mt-6 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {stats.map(([label, value]) => (
              <div key={label} className="card-3d p-4">
                <p className="text-sm text-mist">{label}</p>
                <p className="mt-1 text-3xl font-semibold">
                  <CountUp value={value} />
                </p>
              </div>
            ))}
            <div className="card-3d p-4">
              <p className="text-sm text-mist">Average health</p>
              <p className={`mt-1 text-3xl font-semibold ${healthTone(totals.avg_health)}`}>
                {totals.avg_health === null ? "—" : `${totals.avg_health}`}
              </p>
            </div>
          </section>

          <section className="card-3d mt-6 p-5">
            <h2 className="text-lg font-semibold">Health trend</h2>
            <p className="text-sm text-mist">Score for each scan: before fixes and after the fixes you approved (100 is clean).</p>
            {data.trend.length < 1 ? (
              <p className="mt-6 text-sm text-mist">Run a scan to start the trend.</p>
            ) : (
              <div className="mt-4 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.trend.map((point) => ({ ...point, label: shortDate(point.at) }))}>
                    <CartesianGrid stroke="#E4DCCB" strokeDasharray="3 3" />
                    <XAxis dataKey="label" stroke="#3A3A3A" fontSize={12} />
                    <YAxis domain={[0, 100]} stroke="#3A3A3A" fontSize={12} />
                    <Tooltip
                      contentStyle={{ background: "#FBF8F2", border: "1px solid #E4DCCB", borderRadius: 12, color: "#111111" }}
                      labelFormatter={(_label, payload) => payload?.[0]?.payload?.project || ""}
                    />
                    <Legend />
                    <Line type="monotone" dataKey="before" name="Before fixes" stroke="#C0392B" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="after" name="After approved fixes" stroke="#1E8449" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>

          <section className="mt-8">
            <h2 className="text-lg font-semibold">Recent projects</h2>
            <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {data.projects.map((project) => (
                <div key={project.id} className="card-3d p-4">
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold">{project.name}</p>
                    <span className={`text-lg font-semibold ${healthTone(project.health)}`}>
                      {project.health === null ? "—" : project.health}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-mist">
                    {project.scans} scan{project.scans === 1 ? "" : "s"} · {project.bugs} open bug{project.bugs === 1 ? "" : "s"} ·{" "}
                    {project.last_scan_at ? `last scan ${shortDate(project.last_scan_at)}` : "not scanned yet"}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs">
                    <Link to={`/p/${project.id}/dashboard`} className="rounded-full border border-line px-3 py-1 hover:border-ink">Dashboard</Link>
                    <Link to={`/p/${project.id}/scan`} className="rounded-full border border-line px-3 py-1 hover:border-ink">Scan</Link>
                    <Link to={`/p/${project.id}/fix`} className="rounded-full border border-line px-3 py-1 hover:border-ink">Fix</Link>
                    <Link to={`/p/${project.id}/assistant`} className="rounded-full border border-line px-3 py-1 hover:border-ink">Ask assistant</Link>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

export function GuestNote() {
  return (
    <div className="mt-4 rounded-2xl border border-line bg-panel px-4 py-3 text-sm">
      You're browsing as a guest, so this shows what you opened in this browser.{" "}
      <Link to="/login" className="font-medium underline">Log in</Link> or{" "}
      <Link to="/register" className="font-medium underline">create an account</Link> to keep your history.
    </div>
  );
}
