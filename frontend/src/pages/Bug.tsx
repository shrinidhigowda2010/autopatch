import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import DiffView from "../components/DiffView";
import SeverityBadge from "../components/Severity";
import { usePrefs } from "../components/Shell";
import { explanationFor, percent } from "../lib/format";
import type { Bug } from "../types";

export default function BugPage() {
  const { projectId = "", bugId = "" } = useParams();
  const prefs = usePrefs();
  const [bug, setBug] = useState<Bug | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Bug>(`/api/bugs/${bugId}`).then(setBug).catch((err: Error) => setError(err.message));
  }, [bugId]);

  if (error) return <p className="text-coral">{error}</p>;
  if (!bug) return <p className="text-mist">Loading the bug report…</p>;
  const patch = bug.suggested_patch[0];
  const confidence = bug.severity_and_confidence;

  return (
    <article className="mx-auto max-w-3xl space-y-6">
      <Link to={`/p/${projectId}/explain`} className="text-sm text-lime">Back to explanations</Link>
      <section>
        <h2 className="text-sm uppercase tracking-wide text-mist">Bug details</h2>
        <h1 className="mt-1 text-3xl font-semibold">{bug.bug_details.title}</h1>
        <p className="mt-2 font-mono text-sm text-mist">{bug.bug_details.file}:{bug.bug_details.line} · {bug.bug_details.symbol} · {bug.bug_details.source}</p>
        <p className="mt-3">{bug.bug_details.description}</p>
        <pre className="mt-3 overflow-auto rounded-lg bg-ink p-3 font-mono text-xs">{bug.bug_details.snippet}</pre>
        {bug.bug_details.demo_cache_used && bug.bug_details.cached_root_cause && (
          <p className="mt-3 rounded-lg border border-sky/40 bg-sky/10 p-3 text-sm">Cached model note: {bug.bug_details.cached_root_cause}</p>
        )}
      </section>
      <section>
        <h2 className="text-sm uppercase tracking-wide text-mist">Root cause</h2>
        <p className="mt-2">{explanationFor(prefs.studentMode, prefs.language, bug)}</p>
        <p className="mt-3 text-sm text-mist"><span className="text-paper">What triggers it. </span>{bug.trigger}</p>
      </section>
      <section>
        <h2 className="text-sm uppercase tracking-wide text-mist">Suggested patch</h2>
        {patch ? (
          <div className="mt-3">
            <DiffView before={patch.before_code} after={patch.after_code} diff={patch.diff} />
            <p className="mt-2 text-xs text-mist">Status: {patch.status}. Red is the current code, green is the proposed code, and the block below is the unified diff.</p>
          </div>
        ) : (
          <p className="mt-2 text-mist">No automatic patch for this finding. It stays in the report for a person to decide.</p>
        )}
      </section>
      <section>
        <h2 className="text-sm uppercase tracking-wide text-mist">Test results</h2>
        {bug.test_results.length === 0 ? (
          <p className="mt-2 text-mist">No test run yet. The Test step runs the existing suite and generated edge cases before and after the patch.</p>
        ) : (
          <ul className="mt-2 space-y-2 text-sm">
            {bug.test_results.map((run) => (
              <li key={run.id} className="rounded-lg border border-line p-3">
                Run {run.id} is {run.status}.
                {run.for_this_bug[0] && (
                  <span> This bug’s own tests {run.for_this_bug[0].passed ? "passed" : "failed"}.</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <h2 className="text-sm uppercase tracking-wide text-mist">Severity & confidence</h2>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <SeverityBadge severity={confidence.severity} />
          <span>Confidence {percent(confidence.confidence)}</span>
          {confidence.needs_human_review && <span className="text-amber">needs human review</span>}
        </div>
        <p className="mt-2 text-sm">{confidence.impact}</p>
      </section>
      <section>
        <h2 className="text-sm uppercase tracking-wide text-mist">Change history</h2>
        <ol className="mt-2 space-y-2 text-sm">
          {bug.change_history.map((event) => (
            <li key={event.at + event.message}>
              <span className="font-mono text-xs text-mist">{event.at}</span> {event.message}
            </li>
          ))}
        </ol>
      </section>
    </article>
  );
}
