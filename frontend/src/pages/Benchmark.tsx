import { useEffect, useState } from "react";
import { api } from "../api";
import { PageSkeleton } from "../components/Skeleton";

interface Result {
  detection_rate?: number;
  fix_success_rate?: number;
  false_positive_count?: number;
  false_positive_rate?: number;
  bug_count?: number;
  project_count?: number;
  method?: string;
  note?: string;
  projects?: {
    id: string;
    title: string;
    ground_truth: number;
    detected: number;
    fixed: boolean;
    missed: string[];
    false_positives: { rule_id: string; file: string }[];
  }[];
}

export default function Benchmark() {
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Result>("/api/benchmark").then(setResult).catch((err: Error) => setError(err.message));
  }, []);

  async function run() {
    setBusy(true);
    setError("");
    try {
      setResult(await api<Result>("/api/benchmark/run", { method: "POST" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Benchmark failed.");
    } finally {
      setBusy(false);
    }
  }

  const rate = (value?: number) => (value === undefined ? "—" : `${Math.round(value * 100)}%`);

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-3xl font-semibold">Benchmark</h1>
      <p className="mt-2 text-mist">
        Eight bundled programs, each with a ground-truth bug list. The numbers below are measured by running the scanners and the oracles.
        Gemini is not part of this score.
      </p>
      <button onClick={() => void run()} disabled={busy} className="mt-4 btn-primary disabled:opacity-60">
        {busy ? "Measuring… this takes a minute" : "Run benchmark"}
      </button>
      {error && <p className="mt-4 text-bug">{error}</p>}
      {!result && !error && (
        <div className="mt-6">
          <PageSkeleton label="Loading benchmark results" />
        </div>
      )}
      {result?.note && <p className="mt-4 text-mist">{result.note}</p>}
      {result?.detection_rate !== undefined && (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-line bg-panel p-4"><p className="text-sm text-mist">Detection rate</p><p className="text-3xl">{rate(result.detection_rate)}</p></div>
            <div className="rounded-xl border border-line bg-panel p-4"><p className="text-sm text-mist">Fix success</p><p className="text-3xl">{rate(result.fix_success_rate)}</p></div>
            <div className="rounded-xl border border-line bg-panel p-4"><p className="text-sm text-mist">False positives</p><p className="text-3xl">{result.false_positive_count}</p></div>
          </div>
          <p className="mt-4 text-sm text-mist">{result.method}</p>
          <table className="mt-4 w-full text-left text-sm">
            <thead className="text-mist">
              <tr><th className="py-2">Project</th><th>Truth</th><th>Detected</th><th>Fixed</th><th>False positives</th></tr>
            </thead>
            <tbody>
              {(result.projects || []).map((project) => (
                <tr key={project.id} className="border-t border-line">
                  <td className="py-2">{project.title}</td>
                  <td>{project.ground_truth}</td>
                  <td>{project.detected}</td>
                  <td>{project.fixed ? "yes" : "no"}</td>
                  <td>{project.false_positives.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
