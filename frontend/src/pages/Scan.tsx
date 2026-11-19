import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import FileTree from "../components/FileTree";
import SeverityBadge from "../components/Severity";
import { sourceLabel } from "../lib/format";
import type { Project, Scan } from "../types";

export default function Scan() {
  const { projectId = "" } = useParams();
  const [params] = useSearchParams();
  const [project, setProject] = useState<Project | null>(null);
  const [scan, setScan] = useState<Scan | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const autoStarted = useRef(false);

  useEffect(() => {
    api<Project>(`/api/projects/${projectId}`).then(setProject).catch((err: Error) => setError(err.message));
  }, [projectId]);

  async function run() {
    setBusy(true);
    setError("");
    try {
      const result = await api<Scan>(`/api/projects/${projectId}/scans`, { method: "POST" });
      setScan(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The scan didn't finish. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (params.get("auto") !== "1" || autoStarted.current) return;
    autoStarted.current = true;
    void run();
    // Auto-start scan once when opened from an example project.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const bugs = (scan?.bugs || []).filter((bug) => bug.bug_details.category !== "style");
  const notes = (scan?.bugs || []).filter((bug) => bug.bug_details.category === "style");

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold">Scan</h1>
          <p className="mt-1 max-w-2xl text-mist">
            FixPilot runs trusted checkers (pylint, pyflakes, bandit and a secret scan) and asks Gemini to look for logic
            bugs. Then it merges both into one list. Click any bug to see why it happens.
          </p>
        </div>
        <button onClick={() => void run()} disabled={busy} className="btn-primary disabled:opacity-60">
          {busy ? "Scanning… about 20 seconds" : scan ? "Scan again" : "Run scan"}
        </button>
      </div>
      {error && <p className="mt-4 text-bug">{error}</p>}
      {project && (
        <section className="mt-6 grid gap-4 lg:grid-cols-2">
          <div className="card-3d p-4">
            <h2 className="font-medium">File tree</h2>
            <div className="mt-3 max-h-80 overflow-auto">
              <FileTree nodes={project.tree} />
            </div>
          </div>
          <div className="space-y-4">
            <div className="rounded-xl border border-line bg-panel p-4">
              <h2 className="font-medium">Languages</h2>
              <ul className="mt-2 text-sm text-mist">
                {project.languages.map((lang) => (
                  <li key={lang.name}>{lang.name} · {lang.files} file{lang.files === 1 ? "" : "s"}</li>
                ))}
              </ul>
            </div>
            <div className="rounded-xl border border-line bg-panel p-4">
              <h2 className="font-medium">Dependencies</h2>
              {project.dependencies.length === 0 ? (
                <p className="mt-2 text-sm text-mist">No third-party packages.</p>
              ) : (
                <ul className="mt-2 font-mono text-sm">
                  {project.dependencies.map((dep) => (
                    <li key={dep.name}>{dep.name}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-xl border border-line bg-panel p-4">
              <h2 className="font-medium">Important files</h2>
              <ul className="mt-2 text-sm">
                {project.important.map((item) => (
                  <li key={item.path}><span className="font-mono">{item.path}</span> <span className="text-mist">— {item.reason}</span></li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      )}
      {project && (
        <section className="mt-4 rounded-xl border border-line bg-panel p-4">
          <h2 className="font-medium">Import graph</h2>
          <ul className="mt-2 space-y-1 font-mono text-xs text-mist">
            {project.graph.edges.length === 0 && <li>These files don't import each other.</li>}
            {project.graph.edges.map((edge) => (
              <li key={`${edge.from}-${edge.to}`}>{edge.from} → {edge.to} <span className="text-paper">({edge.kind})</span></li>
            ))}
          </ul>
        </section>
      )}
      {scan && (
        <section className="mt-6">
          <h2 className="text-lg font-medium">{bugs.length} bug{bugs.length === 1 ? "" : "s"}</h2>
          <div className="mt-3 space-y-2">
            {bugs.map((bug) => (
              <Link key={bug.id} to={`/p/${projectId}/explain/${bug.id}`} className="block rounded-xl border border-line bg-panel p-4 hover:border-lime/50">
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityBadge severity={bug.severity_and_confidence.severity} />
                  {bug.severity_and_confidence.needs_human_review && <span className="text-xs text-amber">worth a second look</span>}
                </div>
                <p className="mt-2 font-medium">{bug.bug_details.title}</p>
                <p className="font-mono text-xs text-mist">{bug.bug_details.file}:{bug.bug_details.line} · {sourceLabel(bug.bug_details.source)}</p>
              </Link>
            ))}
          </div>
          {notes.length > 0 && (
            <details className="mt-4 text-sm text-mist">
              <summary>{notes.length} small style notes (not bugs)</summary>
              <ul className="mt-2 space-y-1">
                {notes.map((bug) => (
                  <li key={bug.id}>{bug.bug_details.file}:{bug.bug_details.line} — {bug.bug_details.title}</li>
                ))}
              </ul>
            </details>
          )}
          {scan.tool_notes.length > 0 && (
            <p className="mt-4 font-mono text-xs text-mist">{scan.tool_notes.join(" · ")}</p>
          )}
        </section>
      )}
    </div>
  );
}
