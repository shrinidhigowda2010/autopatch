import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import SeverityBadge from "../components/Severity";
import { usePrefs } from "../components/Shell";
import { explanationFor } from "../lib/format";
import type { Bug, Scan } from "../types";

export default function Explain() {
  const { projectId = "" } = useParams();
  const prefs = usePrefs();
  const [bugs, setBugs] = useState<Bug[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ id: string }[]>(`/api/projects/${projectId}/scans`)
      .then(async (scans) => {
        if (!scans[0]) return;
        const full = await api<Scan>(`/api/scans/${scans[0].id}`);
        setBugs(full.bugs.filter((bug) => bug.bug_details.category !== "style"));
      })
      .catch((err: Error) => setError(err.message));
  }, [projectId]);

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-semibold">Explain</h1>
      <p className="mt-2 text-mist">
        Each note says what input triggers the bug and why the code does the wrong thing.
        {prefs.studentMode ? " Simple explanations are on, so you're seeing the shorter version." : " Want it simpler? Turn on Simple explanations at the top, or switch to ಕನ್ನಡ / हिन्दी."}
      </p>
      {error && <p className="mt-4 text-bug">{error}</p>}
      <div className="mt-6 space-y-3">
        {bugs.length === 0 && <p className="text-mist">No scan yet. Run one from the Scan step.</p>}
        {bugs.map((bug) => (
          <div key={bug.id} className="rounded-xl border border-line bg-panel p-4">
            <SeverityBadge severity={bug.severity_and_confidence.severity} />
            <Link to={`/p/${projectId}/explain/${bug.id}`} className="mt-2 block font-medium hover:underline">
              {bug.bug_details.title}
            </Link>
            <p className="mt-2 text-sm">{explanationFor(prefs.studentMode, prefs.language, bug)}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link to={`/p/${projectId}/explain/${bug.id}`} className="text-xs font-medium underline-offset-2 hover:underline">
                Open report
              </Link>
              <Link
                to={`/p/${projectId}/assistant?bug=${bug.id}`}
                className="rounded-xl border border-line bg-cream px-2.5 py-1 text-xs font-medium hover:border-ink"
              >
                Discuss with Assistant
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
