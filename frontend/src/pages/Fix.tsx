import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import DiffView from "../components/DiffView";
import type { Bug, Scan } from "../types";

export default function Fix() {
  const { projectId = "" } = useParams();
  const [scan, setScan] = useState<Scan | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const scans = await api<{ id: string }[]>(`/api/projects/${projectId}/scans`);
    if (!scans[0]) return;
    setScan(await api<Scan>(`/api/scans/${scans[0].id}`));
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, [projectId]);

  async function decide(patchId: string, action: "accept" | "reject") {
    setError("");
    try {
      await api(`/api/patches/${patchId}/decision`, { method: "POST", body: JSON.stringify({ action }) });
      setMessage(action === "accept" ? "Patch applied to the workspace." : "Patch rejected. The file was left alone.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the decision.");
    }
  }

  async function applySafe() {
    if (!scan) return;
    setError("");
    try {
      const result = await api<{ applied: { title: string }[]; skipped: { title: string }[] }>(
        `/api/scans/${scan.id}/apply-safe`,
        { method: "POST" },
      );
      setMessage(`Applied ${result.applied.length} safe fix(es). Skipped ${result.skipped.length}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nothing was applied.");
    }
  }

  const bugs = (scan?.bugs || []).filter((bug) => bug.suggested_patch.length > 0);

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold">Fix</h1>
          <p className="mt-2 max-w-2xl text-mist">
            A patch touches only the lines the rule needs. It stays a proposal until you accept it.
            “Apply all safe fixes” only writes patches whose confidence is high and whose generated tests passed.
          </p>
        </div>
        <button onClick={() => void applySafe()} className="rounded-lg border border-lime px-4 py-2 text-lime">
          Apply all safe fixes
        </button>
      </div>
      {message && <p className="mt-4 text-good">{message}</p>}
      {error && <p className="mt-4 text-coral">{error}</p>}
      <div className="mt-6 space-y-6">
        {bugs.length === 0 && <p className="text-mist">No patches yet. Run a scan first.</p>}
        {bugs.map((bug: Bug) => {
          const patch = bug.suggested_patch[0];
          return (
            <section key={bug.id} className="rounded-xl border border-line bg-panel p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Link to={`/p/${projectId}/explain/${bug.id}`} className="font-medium hover:text-lime">{bug.bug_details.title}</Link>
                <span className="font-mono text-xs text-mist">{patch.status}</span>
              </div>
              <div className="mt-3">
                <DiffView before={patch.before_code} after={patch.after_code} diff={patch.diff} />
              </div>
              {patch.status === "proposed" && (
                <div className="mt-3 flex gap-2">
                  <button onClick={() => void decide(patch.id, "accept")} className="rounded-lg bg-lime px-3 py-1.5 text-sm font-medium text-ink">Accept</button>
                  <button onClick={() => void decide(patch.id, "reject")} className="rounded-lg border border-line px-3 py-1.5 text-sm">Reject</button>
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
