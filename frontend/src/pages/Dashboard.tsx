import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { PageSkeleton } from "../components/Skeleton";
import CountUp from "../components/CountUp";
import SeverityBadge from "../components/Severity";
import type { Severity } from "../types";

interface Dash {
  counts: {
    findings: number;
    actionable: number;
    needs_review: number;
    by_severity: Record<string, number>;
    by_category: Record<string, number>;
  };
  bugs: { id: string; title: string; severity: Severity; confidence: number; needs_human_review: boolean }[];
  scan: { mode: string } | null;
  health?: { before: number; after: number };
}

export default function Dashboard() {
  const { projectId = "" } = useParams();
  const [data, setData] = useState<Dash | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Dash>(`/api/projects/${projectId}/dashboard`).then(setData).catch((err: Error) => setError(err.message));
  }, [projectId]);

  if (error) return <p className="text-bug">{error}</p>;
  if (!data) return <PageSkeleton label="Loading the dashboard" />;
  const severity = Object.entries(data.counts.by_severity).map(([name, count]) => ({ name, count }));
  const category = Object.entries(data.counts.by_category).map(([name, count]) => ({ name, count }));

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-3xl font-semibold">Dashboard</h1>
      <p className="mt-2 text-mist">
        {data.scan ? "Showing the latest scan for this project." : "Scan the project and this page fills in."}{" "}
        Anything FixPilot is less than 80% sure about is marked for you to double-check.
      </p>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <Stat label="Findings" value={data.counts.findings} />
        <Stat label="Actionable bugs" value={data.counts.actionable} />
        <Stat label="Needs human review" value={data.counts.needs_review} />
      </div>
      {data.health && (
        <div className="card-3d mt-4 p-5">
          <p className="text-sm text-mist">Health score</p>
          <div className="mt-3 flex items-end gap-4">
            <p className="text-4xl font-semibold">
              <CountUp value={data.health.after} />
            </p>
            <p className="mb-1 text-sm text-mist">
              from <CountUp value={data.health.before} /> before repairs
            </p>
          </div>
          <div className="mt-3 h-3 overflow-hidden rounded-full bg-line shadow-emboss">
            <div
              className="h-full rounded-full bg-ink transition-all"
              style={{ width: `${Math.max(4, data.health.after)}%` }}
            />
          </div>
        </div>
      )}
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <ChartCard title="By severity" data={severity} />
        <ChartCard title="By category" data={category} />
      </div>
      <ul className="mt-6 space-y-2">
        {data.bugs.map((bug) => (
          <li key={bug.id}>
            <div className="card-3d flex flex-wrap items-center gap-3 px-3 py-2">
              <Link to={`/p/${projectId}/explain/${bug.id}`} className="flex flex-wrap items-center gap-3">
                <SeverityBadge severity={bug.severity} />
                <span>{bug.title}</span>
              </Link>
              <span className="ml-auto font-mono text-xs text-mist">{Math.round(bug.confidence * 100)}%</span>
              {bug.needs_human_review && <span className="badge-emboss border-review/30 bg-review/10 text-review">needs review</span>}
              <Link
                to={`/p/${projectId}/assistant?bug=${bug.id}`}
                className="rounded-xl border border-line bg-cream px-2.5 py-1 text-xs font-medium hover:border-ink"
              >
                Discuss with Assistant
              </Link>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="card-3d p-4">
      <p className="text-sm text-mist">{label}</p>
      <p className="text-3xl font-semibold">
        <CountUp value={value} />
      </p>
    </div>
  );
}

function ChartCard({ title, data }: { title: string; data: { name: string; count: number }[] }) {
  return (
    <div className="card-3d h-64 p-4">
      <h2 className="mb-2 font-medium">{title}</h2>
      <ResponsiveContainer width="100%" height="85%">
        <BarChart data={data}>
          <CartesianGrid stroke="#E4DCCB" vertical={false} />
          <XAxis dataKey="name" stroke="#3A3A3A" fontSize={12} />
          <YAxis allowDecimals={false} stroke="#3A3A3A" fontSize={12} />
          <Tooltip contentStyle={{ background: "#FBF8F2", border: "1px solid #E4DCCB", color: "#111111" }} />
          <Bar dataKey="count" fill="#111111" radius={4} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
