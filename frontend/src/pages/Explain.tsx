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
        {prefs.studentMode ? " Student mode is on, so the shorter explanation is showing." : " Turn on student mode for a shorter version."}
      </p>
      {error && <p className="mt-4 text-coral">{error}</p>}
      <div className="mt-6 space-y-3">
        {bugs.length === 0 && <p className="text-mist">No scan yet. Run one from the Scan step.</p>}
        {bugs.map((bug) => (
          <Link key={bug.id} to={`/p/${projectId}/explain/${bug.id}`} className="block rounded-xl border border-line bg-panel p-4">
            <SeverityBadge severity={bug.severity_and_confidence.severity} />
            <p className="mt-2 font-medium">{bug.bug_details.title}</p>
            <p className="mt-2 text-sm">{explanationFor(prefs.studentMode, prefs.language, bug)}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
