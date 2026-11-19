import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
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
}

export default function Dashboard() {
  const { projectId = "" } = useParams();
  const [data, setData] = useState<Dash | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Dash>(`/api/projects/${projectId}/dashboard`).then(setData).catch((err: Error) => setError(err.message));
  }, [projectId]);

  if (error) return <p className="text-coral">{error}</p>;
  if (!data) return <p className="text-mist">Loading the dashboard…</p>;
  const severity = Object.entries(data.counts.by_severity).map(([name, count]) => ({ name, count }));
  const category = Object.entries(data.counts.by_category).map(([name, count]) => ({ name, count }));

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-3xl font-semibold">Dashboard</h1>
      <p className="mt-2 text-mist">
        {data.scan ? `Latest scan ran in ${data.scan.mode} mode.` : "Scan the project to fill this page."}{" "}
        Findings under 80% confidence are marked for a person to check.
      </p>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <Stat label="Findings" value={data.counts.findings} />
        <Stat label="Actionable bugs" value={data.counts.actionable} />
        <Stat label="Needs human review" value={data.counts.needs_review} />
      </div>
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <ChartCard title="By severity" data={severity} />
        <ChartCard title="By category" data={category} />
      </div>
      <ul className="mt-6 space-y-2">
        {data.bugs.map((bug) => (
          <li key={bug.id}>
            <Link to={`/p/${projectId}/explain/${bug.id}`} className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-panel px-3 py-2">
              <SeverityBadge severity={bug.severity} />
              <span>{bug.title}</span>
              <span className="ml-auto font-mono text-xs text-mist">{Math.round(bug.confidence * 100)}%</span>
              {bug.needs_human_review && <span className="text-xs text-amber">needs human review</span>}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-line bg-panel p-4">
      <p className="text-sm text-mist">{label}</p>
      <p className="text-3xl font-semibold">{value}</p>
    </div>
  );
}

function ChartCard({ title, data }: { title: string; data: { name: string; count: number }[] }) {
  return (
    <div className="h-64 rounded-xl border border-line bg-panel p-4">
      <h2 className="mb-2 font-medium">{title}</h2>
      <ResponsiveContainer width="100%" height="85%">
        <BarChart data={data}>
          <CartesianGrid stroke="#2c382f" vertical={false} />
          <XAxis dataKey="name" stroke="#9aab9d" fontSize={12} />
          <YAxis allowDecimals={false} stroke="#9aab9d" fontSize={12} />
          <Tooltip contentStyle={{ background: "#171d18", border: "1px solid #2c382f" }} />
          <Bar dataKey="count" fill="#dff25a" radius={4} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
